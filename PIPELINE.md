# PIPELINE.md — How this project works, end to end

A plain-language walkthrough of what this framework is, what happens when you
run `pytest`, and how each folder plugs into that flow. Read this before
`README.md` if you're new to the repo.

---

## 1. What problem this solves

An **MCP server** (Model Context Protocol) exposes *tools*, *resources* and
*prompts* that an AI assistant can call. Two things need testing:

1. **The server itself** — do its tools exist, accept the right arguments,
   return the right shape, and fail *cleanly* on bad input?
2. **The UI in front of it** — does the web app that talks to that server
   still work after a front-end refactor?

Classic automation handles both, but breaks constantly: selectors drift,
pixel-diffs flag anti-aliasing as a "failure", and flaky tests eat hours.
This framework is **Playwright + pytest for the deterministic parts, with an
LLM bolted on only where determinism runs out** — repairing broken selectors,
triaging visual diffs, root-causing flakes, and inventing edge-case inputs.

Every AI feature is a flag. Turn them all off and you still have a working,
ordinary Playwright + pytest suite.

---

## 2. The layer cake

```
                         pytest  (entry point)
                            |
                    conftest.py  -- fixtures + failure hooks
                            |
        +-------------------+-------------------+
        |                   |                   |
   config/              core/                  ai/
   settings             mcp_client             llm_client --- Anthropic API
   environments         browser_manager        self_healing
        |                   |                  visual_ai
        |                   |                  flaky_analyzer
        |                   |                  mcp_fuzzer
        |                   |                  assertion_oracle
        |                   |                  nl_test_generator
        |                   |                  synthetic_data_generator
        |                   |                   |
        +-------------------+-------------------+
                            |
                    pages/  (Page Objects, self-healing built in)
                            |
                        tests/  (unit - mcp - ui - ai)
                            |
                 utils/  -- logger - screenshots - reports/
```

**Dependency rule:** everything flows downward. `ai/` may use `core/`,
`pages/` may use `ai/`, tests use all of them. Nothing lower imports upward.

---

## 3. The run pipeline, step by step

### Stage 0 — Configuration resolves (`config/settings.py`)

Happens once, at import time, before any test is collected.

```
.env  ----+
          +--->  Settings.load()  --->  a single `settings` object
environments.yaml
```

- `config/environments.yaml` holds one block per environment — `local`,
  `staging`, `ci` — with `base_url`, `headless`, and an `mcp_server` block
  (transport, command, args or url).
- `TEST_ENV` picks the block. Default: `local`.
- **Environment variables always win over YAML** (`config/settings.py:76`), so
  CI or a one-off shell export overrides the file without editing it.
- Out of the box `local` points at the bundled `examples/demo_server.py`, so a
  fresh clone runs green with no setup.

Feature flags live here too: `AI_SELF_HEALING_ENABLED`,
`AI_VISUAL_TRIAGE_ENABLED`, `AI_FLAKY_ANALYSIS_ENABLED`, plus `HEADLESS` and
`SCREENSHOT_ON_FAILURE`.

### Stage 1 — Fixtures build the world (`conftest.py`)

pytest supplies whatever a test's signature names, and only that:

| Fixture | Scope | What it gives you |
|---|---|---|
| `browser_manager` | module | A launched Playwright browser |
| `context` | function | A fresh browser context (clean cookies/storage) |
| `page` | function | A fresh tab |
| `self_healing` | function | AI locator resolver bound to that page |
| `mcp_client` | function | A live, initialized MCP session |
| `visual_ai` | function | Screenshot comparator |
| `flaky_analyzer` | function | Failure-log root-cause analyzer |

Two deliberate design choices worth knowing:

- **`browser_manager` is module-scoped, not session-scoped.** Playwright's
  sync API keeps an asyncio loop alive while a browser is open, which makes
  every `pytest-asyncio` test that runs *after* a UI test blow up with
  "Runner.run() cannot be called from a running event loop". Module scope
  still reuses one browser per UI file, but tears it down before other
  modules' async tests run.
- **`mcp_client` skips instead of erroring** when no server is configured or
  the command isn't on PATH — so the suite stays green on a clone that hasn't
  been pointed at a real server yet.

### Stage 2 — The MCP session opens (`core/mcp_client.py`)

`MCPTestClient` wraps the official `mcp` SDK so tests never touch transports.

```
MCPTestClient.stdio("python", ["examples/demo_server.py"])
        |                    or  .sse("https://.../mcp")
        v
  background lifecycle task
        |  opens transport -> initialize() -> signals ready
        |  parks until stop is requested
        v
  list_tools() - call_tool() - list_resources() - read_resource()
  list_prompts() - get_prompt()      -> plain dicts, not SDK types
```

Two problems it solves for you:

- **The single-task rule.** The SDK's transports use anyio cancel scopes,
  which must be entered and exited in the *same* task — but pytest-asyncio
  runs fixture setup and teardown in different tasks. So the whole transport
  lifetime lives inside one background task (`_lifecycle`,
  `core/mcp_client.py:111`).
- **`python` isn't `python`.** A stdio server configured as `python` must
  launch in the same virtualenv as the test run, and bare `python` doesn't
  exist on stock macOS. `resolve_server_command()` maps it to
  `sys.executable`; anything else (node, npx, a binary path) passes through.

Tool results come back as an `MCPCallResult` with a `.text` property that
concatenates text blocks — so assertions read `assert "pong" in result.text`
instead of digging through SDK objects.

### Stage 3 — The test body runs

Four suites, each with its own marker (`pytest.ini`):

| Suite | Marker | Needs | What it proves |
|---|---|---|---|
| `tests/unit` | `unit` | nothing — no browser, no network, no API key | Settings layering, MCP client shape, LLM client, and every AI module against mocks |
| `tests/mcp` | `mcp` | a running MCP server | Tools, resources and prompts behave over a real session |
| `tests/ui` | `ui` | a browser | Page objects drive the real UI |
| `tests/ai` | `ai` | `ANTHROPIC_API_KEY` | The AI-assisted paths actually work live |

`tests/unit` is the one that runs everywhere, every time, in seconds. The
others degrade gracefully when their dependency is missing.

### Stage 4 — UI actions go through self-healing (`pages/` + `ai/self_healing.py`)

Every page object extends `BasePage`, and `BasePage.find()` routes through the
healer. So you write:

```python
self.find(
    description="the main page heading for the practice home page",
    selector='h1:has-text("Master QA Testing Through Practice")',
)
```

and this happens:

```
        find(description, selector)
                 |
      try the original selector (5s)
        +--------+--------+
     found            timeout
        |                 |
     return         AI disabled? --> raise (plain Playwright behaviour)
                          |
              send trimmed DOM (12k chars) + description to the LLM
                          |
                 LLM proposes a replacement selector
                          |
                  retry once with the proposal
                    +-----+-----+
                 works        fails
                    |            |
        log HealRecord      log HealRecord, then raise
        return locator      naming both selectors
```

The important part is the **log**. Every heal — successful or not — is
recorded as a `HealRecord` on both the locator *and* the `Page` object, so the
healer is a diagnostic telling you which selector to fix permanently, not a
crutch that hides rot forever.

### Stage 5 — Failure hooks fire (`conftest.py:117`)

When a test fails, `pytest_runtest_makereport` runs before the report is
finalized:

```
test fails
    |
    +--> page in fixtures + SCREENSHOT_ON_FAILURE?
    |        +--> full-page PNG -> reports/screenshots/<test_name>.png
    |
    +--> any HealRecords on the page?
             +--> reports/<test_name>_self_heal.json
```

Heals are collected from the page-level registry first, so heals from *any*
locator attached to that page — page objects included — get captured, not just
the ones from the `self_healing` fixture.

### Stage 6 — Reports land in `reports/`

```
reports/
├── report.html              <- pytest-html, self-contained (pytest.ini addopts)
├── screenshots/*.png        <- failure captures
├── baselines/*.png          <- visual regression baselines
└── *_self_heal.json         <- AI artifacts
```

`reports/` is gitignored — it's run output, not source.

---

## 4. The AI modules, and when each one fires

All seven go through **one** file: `ai/llm_client.py`. That's the single place
the Anthropic SDK is touched, with three call shapes (`ask`, `ask_json`,
`ask_with_image`), retries via tenacity, and a lazy singleton so importing an
AI module never requires an API key up front. Swapping model or provider is a
one-file change.

| Module | Fires when | What it does |
|---|---|---|
| `self_healing.py` | Automatically, on any locator timeout | Proposes a replacement selector from the live DOM, retries once, logs the heal |
| `visual_ai.py` | You call `visual_ai.compare(...)` | **Pixel diff first** (fast, free, deterministic); escalates to a vision call *only when there is a diff*, to classify it `regression` vs `noise` with a reason |
| `flaky_analyzer.py` | You feed it logs from N failing runs | Classifies root cause — `race_condition`, `selector_drift`, `test_data_pollution`, `genuine_bug`, … — and suggests a concrete fix |
| `mcp_fuzzer.py` | You point it at a tool's `input_schema` | Generates adversarial arguments (type confusion, injection strings, unicode, oversized payloads, missing fields) and flags the ones that **crash** rather than returning a clean validation error |
| `assertion_oracle.py` | You call `assert_semantic(...)` | LLM-as-judge for natural-language output where exact match is too brittle. An escape hatch — prefer a real assertion wherever one exists |
| `nl_test_generator.py` | You run it by hand | Turns an English scenario into structured Playwright steps or MCP calls. **Generation-time only** — you review and commit the output; it never executes unreviewed AI output against a target |
| `synthetic_data_generator.py` | You call it with a JSON schema | Realistic test records, validated against the schema, including boundary cases |

The design line running through all of them: **cheap and deterministic first,
LLM only where that runs out, and always log what the AI decided.**

---

## 5. The MCP fuzzing pipeline (the most interesting path)

```
list_tools()  -->  for each tool, take its input_schema
                            |
                  LLM generates N adversarial argument sets
                            |
                  call_tool() each one against the live server
                            |
                  +---------+----------+
        clean validation error    unhandled crash / raw exception
                  |                     |
               expected            <-- FuzzFinding: this is the bug
```

The insight: a well-built MCP tool should reject garbage with a *clean* error.
A tool that throws a raw unhandled exception on bad input is the actual defect
— and that gap is what this catches faster than a human hand-writing edge
cases.

---

## 6. CI pipeline (`.github/workflows/tests.yml`)

Runs on every push to `main` and every pull request, ordered cheapest-first so
failures surface fast:

```
checkout -> setup-python 3.11 (pip cache) -> pip install
    |
    +-- ruff check .
    +-- mypy --ignore-missing-imports .
    +-- pytest tests/unit         <- hermetic: no browser, no network, no key
    |
    +-- playwright install chromium   (the expensive step, deliberately late)
    +-- pytest -m "not ai" --reruns 1
    |
    +-- pytest -m "ai"            <- only if ANTHROPIC_API_KEY is present
    |                                (secrets are empty on fork PRs, so the
    |                                 key is hoisted into job env first)
    |
    +-- upload reports/ as an artifact, always
```

---

## 7. Running it yourself

```bash
make install          # pip install -r requirements.txt
make browsers         # playwright install --with-deps chromium
cp .env.example .env  # add ANTHROPIC_API_KEY only if you want the AI features

make test-unit        # seconds, needs nothing
make test-fast        # everything except AI-dependent and slow tests
make test-mcp         # MCP server suite
make test-ui          # browser suite
make test             # all of it
```

Point it at your own server by editing the `mcp_server` block in
`config/environments.yaml`, or without touching the file at all:

```bash
MCP_SERVER_COMMAND=node MCP_SERVER_ARGS=dist/server.js pytest -m mcp
BASE_URL=http://localhost:5173 pytest -m ui
```

---

## 8. Where to add things

| You want to… | Touch |
|---|---|
| Test a new page | New class in `pages/` extending `BasePage`, new file in `tests/ui/` |
| Test a new MCP tool | New test in `tests/mcp/`, using the `mcp_client` fixture |
| Add an environment | New block in `config/environments.yaml` |
| Swap the LLM or model | `ai/llm_client.py` — the only file that touches the SDK |
| Turn off an AI feature | An `AI_*_ENABLED=false` flag in `.env` — no code change |
| Add a new AI capability | New module in `ai/`, built on `get_llm_client()` |
