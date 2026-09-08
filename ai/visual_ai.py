"""AI-assisted visual regression triage.

Pixel-diffing alone flags every anti-aliasing shift and font-rendering
difference as a failure, which trains teams to ignore visual test results.
This module does a cheap pixel diff first (fast, free, deterministic) and
only escalates to the LLM vision call when there IS a diff, asking it to
classify the diff as a meaningful UI regression vs. rendering noise, and to
explain why — cutting down false-positive triage time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

from ai.llm_client import get_llm_client, strip_code_fences

TRIAGE_SYSTEM_PROMPT = """You are a visual regression triage assistant for a
test automation suite. You will see two screenshots: BEFORE (baseline) and
AFTER (current run), plus a computed pixel-diff percentage. Decide whether the
difference is a meaningful UI regression (layout shift, missing element, broken
styling, wrong content) or benign noise (anti-aliasing, font hinting, a
timestamp/animation frame, dynamic ad content). Respond as JSON:
{"verdict": "regression" | "noise", "confidence": 0-1, "reason": "..."}"""


@dataclass
class VisualDiffResult:
    diff_percentage: float
    diff_image_path: str | None
    ai_verdict: str | None = None
    ai_confidence: float | None = None
    ai_reason: str | None = None
    size_mismatch: bool = False

    @property
    def is_meaningful_regression(self) -> bool:
        return self.size_mismatch or self.ai_verdict == "regression"


class VisualAIComparator:
    def __init__(self, pixel_diff_threshold: float = 0.1, ai_enabled: bool = True) -> None:
        self.pixel_diff_threshold = pixel_diff_threshold
        self.ai_enabled = ai_enabled

    def compare(self, baseline_path: str | Path, current_path: str | Path,
                diff_output_path: str | Path | None = None) -> VisualDiffResult:
        baseline = Image.open(baseline_path).convert("RGB")
        current = Image.open(current_path).convert("RGB")

        size_mismatch = baseline.size != current.size
        if size_mismatch:
            # A dimension change is itself a regression signal (layout growth,
            # clipped viewport) — flag it rather than resizing it away, but
            # still resize so the pixel diff and AI triage below can run.
            current = current.resize(baseline.size)

        diff = ImageChops.difference(baseline, current)
        diff_arr = np.array(diff)
        # A pixel counts as different if ANY of its channels moved past the
        # noise floor — dividing by the flat array size would count channels,
        # understating the true differing-pixel percentage by up to 3x.
        changed_pixels = (diff_arr > 10).any(axis=-1)
        diff_percentage = float(changed_pixels.mean() * 100)

        diff_path_str = None
        if diff_percentage > 0 and diff_output_path:
            diff.save(diff_output_path)
            diff_path_str = str(diff_output_path)

        result = VisualDiffResult(
            diff_percentage=diff_percentage,
            diff_image_path=diff_path_str,
            size_mismatch=size_mismatch,
        )

        if diff_percentage <= self.pixel_diff_threshold and not size_mismatch:
            return result  # identical enough — no need to spend an LLM call

        if self.ai_enabled:
            self._classify_with_ai(result, baseline_path, current_path, diff_percentage)

        return result

    def _classify_with_ai(
        self, result: VisualDiffResult, baseline_path, current_path, diff_percentage: float
    ) -> None:
        try:
            combined = self._side_by_side(baseline_path, current_path)
            buf = BytesIO()
            combined.save(buf, format="PNG")
            raw = get_llm_client().ask_with_image(
                prompt=(
                    f"Pixel diff: {diff_percentage:.3f}% of pixels differ. Left half is BEFORE, "
                    "right half is AFTER. Respond as JSON: "
                    '{"verdict": "regression"|"noise", "confidence": 0-1, "reason": "..."}'
                ),
                image_bytes=buf.getvalue(),
                system=TRIAGE_SYSTEM_PROMPT,
            )
            parsed = json.loads(strip_code_fences(raw))
            result.ai_verdict = parsed.get("verdict")
            result.ai_confidence = parsed.get("confidence")
            result.ai_reason = parsed.get("reason")
        except Exception as exc:  # noqa: BLE001 - triage is advisory, must not crash the test
            result.ai_reason = f"AI triage failed: {exc}"

    @staticmethod
    def _side_by_side(baseline_path, current_path) -> Image.Image:
        a = Image.open(baseline_path).convert("RGB")
        b = Image.open(current_path).convert("RGB").resize(a.size)
        combined = Image.new("RGB", (a.width * 2, a.height))
        combined.paste(a, (0, 0))
        combined.paste(b, (a.width, 0))
        return combined
