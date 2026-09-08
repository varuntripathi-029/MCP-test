"""Hermetic tests for the deterministic half of VisualAIComparator —
the pixel-diff math and size-mismatch handling need no LLM and no browser."""
import pytest
from PIL import Image

from ai.visual_ai import VisualAIComparator, VisualDiffResult

pytestmark = pytest.mark.unit


def _solid(tmp_path, name: str, color: tuple[int, int, int], size=(100, 100)):
    path = tmp_path / name
    Image.new("RGB", size, color).save(path)
    return path


def test_identical_images_have_zero_diff(tmp_path):
    a = _solid(tmp_path, "a.png", (200, 30, 30))
    b = _solid(tmp_path, "b.png", (200, 30, 30))

    result = VisualAIComparator(ai_enabled=False).compare(a, b)

    assert result.diff_percentage == 0.0
    assert not result.size_mismatch
    assert not result.is_meaningful_regression


def test_fully_different_images_report_100_percent(tmp_path):
    """Every pixel differs — the percentage must count pixels, not channels
    (a single-channel shift used to be under-reported by up to 3x)."""
    a = _solid(tmp_path, "a.png", (0, 0, 0))
    b = _solid(tmp_path, "b.png", (0, 0, 255))  # only the blue channel moves

    result = VisualAIComparator(ai_enabled=False).compare(a, b)

    assert result.diff_percentage == pytest.approx(100.0)


def test_partial_diff_percentage_matches_changed_region(tmp_path):
    a = _solid(tmp_path, "a.png", (255, 255, 255))
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(50):  # repaint the left half: exactly 50% of pixels
        for y in range(100):
            img.putpixel((x, y), (0, 0, 0))
    b = tmp_path / "b.png"
    img.save(b)

    result = VisualAIComparator(ai_enabled=False).compare(a, b)

    assert result.diff_percentage == pytest.approx(50.0)


def test_size_mismatch_is_flagged_as_regression(tmp_path):
    a = _solid(tmp_path, "a.png", (10, 10, 10), size=(100, 100))
    b = _solid(tmp_path, "b.png", (10, 10, 10), size=(100, 140))

    result = VisualAIComparator(ai_enabled=False).compare(a, b)

    assert result.size_mismatch
    assert result.is_meaningful_regression


def test_sub_threshold_noise_skips_ai(tmp_path):
    a = _solid(tmp_path, "a.png", (128, 128, 128))
    b = _solid(tmp_path, "b.png", (128, 128, 128))

    # ai_enabled=True but no API key configured in unit tests: if the noise
    # gate failed to short-circuit, this would raise from get_llm_client().
    result = VisualAIComparator(pixel_diff_threshold=0.5, ai_enabled=True).compare(a, b)

    assert result.ai_verdict is None


def test_diff_image_written_when_requested(tmp_path):
    a = _solid(tmp_path, "a.png", (0, 0, 0))
    b = _solid(tmp_path, "b.png", (255, 255, 255))
    out = tmp_path / "diff.png"

    result = VisualAIComparator(ai_enabled=False).compare(a, b, diff_output_path=out)

    assert result.diff_image_path == str(out)
    assert out.exists()


def test_is_meaningful_regression_follows_ai_verdict():
    assert VisualDiffResult(5.0, None, ai_verdict="regression").is_meaningful_regression
    assert not VisualDiffResult(5.0, None, ai_verdict="noise").is_meaningful_regression
