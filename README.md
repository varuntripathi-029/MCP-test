# MCP Test Framework (Playwright + Python + AI)

An AI-augmented test automation framework for **Model Context Protocol (MCP) servers** and any UI in front of them, built on **Playwright (Python)** and **pytest**.

It gives you two things at once:
1. A normal, deterministic test framework (page objects, fixtures, MCP client, reporting) that works with **zero AI dependency**.
2. A set of **opt-in AI modules** (`ai/`) that plug into that framework to reduce maintenance burden and catch things static assertions miss — self-healing locators, visual regression triage, MCP fuzzing, flaky-test root-causing, and more.

Every AI feature is behind a flag in `.env` / `config/settings.py` and degrades gracefully (raises a clear error or skips) if `ANTHROPIC_API_KEY` isn't set — the core suite never depends on AI to run.

---

## 1. Project layout

```
mcp-test-framework/
├── conftest.py              # pytest fixtures: browser, page, mcp_client, AI helpers
├── pytest.ini
├── config/
│   ├── settings.py          # env-driven Settings singleton
│   └── environments.yaml    # per-environment MCP server / base_url config
├── core/
│   ├── mcp_client.py        # async wrapper around the official `mcp` SDK (stdio + SSE)
│   └── browser_manager.py   # Playwright browser/context lifecycle
├── examples/
│   └── demo_server.py       # bundled FastMCP server the MCP tests run against by default
├── ai/                       # every AI-assisted technique lives here, one file each
│   ├── llm_client.py         # shared Anthropic client (text, JSON, vision)
│   ├── self_healing.py       # self-healing Playwright locators
│   ├── visual_ai.py          # pixel-diff + AI visual regression triage
│   ├── nl_test_generator.py  # English scenario -> Playwright/MCP steps
│   ├── flaky_analyzer.py     # AI root-cause analysis for flaky tests
│   ├── synthetic_data_generator.py # synthetic test data from a JSON schema
│   ├── mcp_fuzzer.py         # AI-generated adversarial MCP tool inputs
│   └── assertion_oracle.py   # LLM-as-judge semantic assertions
├── pages/                    # Page Object Model, self-healing by default
├── tests/
│   ├── unit/                 # hermetic tests: no browser, network, server, or API key
│   ├── mcp/                  # tests that talk to the MCP server directly
│   ├── ui/                   # tests that drive a browser
│   └── ai/                   # tests that exercise the AI modules themselves
├── utils/                    # logger, screenshot helper, AI-artifact reporter
└── reports/                  # HTML report, screenshots, AI artifacts (gitignored)
```

---

## 2. Setup

```bash
python -m venv .venv && source .venv/bin/activate
make install                 # pip install -r requirements.txt
make browsers                # playwright install --with-deps chromium

cp .env.example .env
# fill in ANTHROPIC_API_KEY if you want the AI features
```

Out of the box, `tests/mcp/` runs against the bundled `examples/demo_server.py`
(a ~40-line FastMCP server with example tools, a resource, and a prompt), so
`make test-mcp` is green on a fresh clone with no external setup. To test your
real server, point `MCP_SERVER_COMMAND` / `MCP_SERVER_ARGS` (or the
`mcp_server` block in `config/environments.yaml`) at it — a `python`/`python3`
command is automatically resolved to the interpreter running pytest, so the
server sees the same virtualenv.

Run tests:

```bash
make test          # everything
make test-unit      # tests/unit (hermetic — no browser, network, or API key)
make test-mcp       # -m mcp   (talks to the MCP server; skips if none configured)
make test-ui         # -m ui    (drives a browser)
make test-ai          # -m ai    (requires ANTHROPIC_API_KEY)
make test-fast          # -m "not ai and not slow"   (CI-friendly, no API key needed)
make lint typecheck       # ruff + mypy (pip install -e ".[dev]" first)
```

`TEST_ENV=staging pytest` switches which block of `config/environments.yaml` is loaded.

By default, the UI examples point at `https://rahulshettyacademy.com/practice`. If you want to override it for local experimentation, set `BASE_URL` before running pytest.

---

## 3. How AI is integrated

Each technique is a standalone module in `ai/`, built on one shared `LLMClient` (`ai/llm_client.py`, using `claude-sonnet-5` by default — swap the model or provider in one place). None of them are required for the framework to work; they're opt-in accelerators layered on top of deterministic Playwright/MCP assertions.

| # | Technique | Module | What it does | Where it plugs in |
|---|-----------|--------|---------------|--------------------|
| 1 | **Self-healing locators** | `ai/self_healing.py` | When a selector times out, sends the trimmed DOM + a plain-English element description to the LLM, gets back a replacement selector, retries once, and logs every heal. | `pages/base_page.py`, `conftest.py` (`self_healing` fixture), auto-attached to failure reports |
| 2 | **AI visual regression triage** | `ai/visual_ai.py` | Runs a cheap pixel-diff first; only if pixels differ does it send before/after screenshots to the LLM to classify the diff as a real regression vs. rendering noise (anti-aliasing, timestamps, animations), with a confidence + reason. | `visual_ai` fixture, any UI test comparing screenshots |
| 3 | **Natural-language → test generation** | `ai/nl_test_generator.py` | Converts an English scenario into structured Playwright actions or MCP tool-call steps; can render the steps as literal pytest source for a human to review and commit. | Design-time tool, not wired into CI execution by default (by design — output is reviewed before merging) |
| 4 | **MCP tool fuzzing** | `ai/mcp_fuzzer.py` | Given a tool's `input_schema`, asks the LLM for adversarial argument sets (type confusion, injection strings, unicode, oversized payloads, missing required fields) and runs them against a live `MCPTestClient`, flagging unhandled crashes vs. clean validation errors. | `tests/mcp/test_mcp_tools.py::test_fuzz_first_tool_for_crashes` |
| 5 | **Flaky test root-cause analysis** | `ai/flaky_analyzer.py` | Feed it a test name + logs from several failing runs; it classifies the likely cause (race condition, hardcoded wait, test-data pollution, selector drift, network flakiness, environment issue, genuine bug) and suggests a fix. | `flaky_analyzer` fixture; typically run from a CI job that collects logs from `pytest-rerunfailures` reruns |
| 6 | **Synthetic test data generation** | `ai/synthetic_data_generator.py` | Given a JSON schema, generates realistic records plus at least one boundary/edge case (empty string, max length, unicode, negative number). | Form-fill UI tests, MCP tool argument fixtures |
| 7 | **LLM-as-judge assertions** | `ai/assertion_oracle.py` | For outputs with no single correct string (a generated summary, an LLM-backed tool's response), asks the model to judge whether the output satisfies a natural-language expectation, strictly. `assert_semantic()` is a pytest-ready helper. | Use sparingly — prefer deterministic assertions wherever possible |
| 8 | **AI-assisted assertion suggestion** | `ai/assertion_oracle.py::suggest_assertions` | Given a page/response description, proposes a list of concrete assertions a human can turn into real test code — an exploratory-testing aid. | Manual/exploratory test design |

### Design principles behind the AI layer

- **Deterministic first, AI as fallback.** Self-healing only triggers after the real selector times out; visual AI only escalates after a nonzero pixel diff. AI is never the primary check.
- **Every AI decision is logged and attachable to the report.** `conftest.py`'s failure hook writes self-heal logs to `reports/<test>_self_heal.json` so a human reviews and fixes the underlying selector rather than silently depending on AI forever.
- **Generation-time vs. run-time separation.** `nl_test_generator.py` produces code/steps for a human to review and commit — it does not execute unreviewed AI output in CI. `mcp_fuzzer.py`, by contrast, is designed to run unattended because its "assertion" (no crash) is deterministic even though its *inputs* are AI-generated.
- **One shared LLM client.** Swapping models/providers, adding caching, or disabling AI globally is a one-line change in `ai/llm_client.py`, not a per-module change.

---

## 4. Other AI techniques and tools worth integrating

Techniques implemented above, plus adjacent ones you can add as the suite grows:

**Techniques**
- **Self-healing locators** — implemented (`ai/self_healing.py`).
- **Visual AI regression triage** — implemented (`ai/visual_ai.py`).
- **LLM-as-judge / semantic assertions** — implemented (`ai/assertion_oracle.py`).
- **AI-generated edge-case/fuzz inputs** — implemented (`ai/mcp_fuzzer.py`, `ai/synthetic_data_generator.py`).
- **Flaky-test root-cause classification** — implemented (`ai/flaky_analyzer.py`).
- **NL → test-case generation** — implemented (`ai/nl_test_generator.py`).
- **Computer-use / agentic exploratory testing** — an agent (e.g. Claude with computer-use / browser tools) drives the app autonomously from a high-level goal ("find and report any broken flows in checkout") instead of a scripted path. Good for exploratory smoke coverage between scripted regression runs, not as a replacement for it.
- **Schema-drift / semantic diffing of MCP responses** — instead of exact-match on a tool's JSON output, diff two responses semantically (same meaning, different wording/ordering) to catch breaking changes in an MCP server's contract without pinning to exact strings.
- **AI-assisted test prioritization** — rank a large regression suite by predicted likelihood of catching a regression in the current diff (via commit/diff summarization + historical failure correlation), to pick a fast subset for pre-merge gating.
- **Log/trace summarization for failure triage** — summarize a failing test's full Playwright trace + console/network logs into a one-paragraph likely cause, attached to the HTML report, so a human doesn't open the trace viewer for every failure.
- **AI-generated Page Objects from a live page** — point at a URL, have the LLM propose a first-draft Page Object (semantic selectors, method names) from the DOM, for a human to refine.

**Tools/platforms in this space** (beyond the Anthropic API used here):
| Tool | Category | Notes |
|---|---|---|
| Anthropic Claude API (`anthropic` SDK) | LLM provider | Used by every module in `ai/` here; supports text, JSON, and vision in one client. |
| Playwright Trace Viewer + `pytest-playwright` | Native tracing | Not AI itself, but the raw material AI log-summarization/flaky-analysis modules consume. |
| Applitools Eyes / Percy | Visual AI SaaS | Purpose-built visual regression with their own AI diffing — an alternative or complement to `ai/visual_ai.py` if you want a managed baseline store and dashboard. |
| Healenium | Open-source self-healing | Java/Selenium-native self-healing proxy; `ai/self_healing.py` is the from-scratch Python/Playwright/LLM equivalent used here. |
| LangChain / LangGraph | Orchestration | Useful if AI modules grow into multi-step agents (e.g. chaining fuzz-generate → execute → re-prompt-on-failure) rather than single LLM calls. |
| MCP Inspector (`@modelcontextprotocol/inspector`) | Manual MCP debugging | Node-based GUI for manually poking an MCP server; complements this framework's automated `tests/mcp/` suite during development. |
| Playwright Codegen | Non-AI, but adjacent | `playwright codegen` records real clicks into a script — a good "ground truth" companion to `ai/nl_test_generator.py`'s generated steps. |
| OpenAI/GPT-4V, Google Gemini | Alternative LLM providers | `ai/llm_client.py` is the single swap point if you want to try a different model for vision-heavy tasks (visual triage) vs. text-heavy tasks (fuzzing, semantic assertions). |

---

## 5. Writing a new MCP test

```python
import pytest

@pytest.mark.mcp
async def test_my_tool(mcp_client):
    result = await mcp_client.call_tool("my_tool", {"query": "hello"})
    assert not result.is_error
    assert "expected substring" in result.text
```

## 6. Writing a new UI test with self-healing

```python
from pages.example_page import PracticeHomePage

def test_practice_home_loads(page):
    home = PracticeHomePage(page)
    home.open()

    assert page.title() == "QA Automation Practice Sites | Playwright, Selenium & API Testing"
    assert home.browse_practice_button().is_visible()
```

If a selector like the hero heading or the practice-card title changes, the test doesn't fail outright — it logs a heal attempt, and if the AI-proposed selector works, the test passes with a warning in `reports/<test>_self_heal.json`. Treat that file as a to-do list for updating the real selector, not a permanent fix.

To run just these examples:

```bash
source .venv/bin/activate
make test-ui
```

## 7. CI

`.github/workflows/tests.yml` runs ruff, mypy, and the hermetic unit suite first (fast, no browser or key needed), then `pytest -m "not ai"` (no API key required), and a final `pytest -m "ai"` step only when `ANTHROPIC_API_KEY` is available as a secret — so AI-dependent tests never block CI for contributors/forks without the key.

**Sync/async note:** UI tests use Playwright's *sync* API and MCP tests use asyncio. While a sync-Playwright browser is alive it parks a running event loop on the main thread, which breaks any pytest-asyncio test that runs afterwards — that's why the `browser_manager` fixture is module-scoped (torn down when a UI test module finishes), not session-scoped. Keep UI tests and async tests in separate modules.
