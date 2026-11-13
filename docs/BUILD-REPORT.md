# Build report: llm-test-generator v0.1.0

Builder: Claude Opus 5.5 (Claude Code session in `C:\Cerebro`), 2026-11-12.
Local commits only: no remote, no push. Tag `v0.1.0` (annotated, local).

## Folder tree

```text
llm-test-generator/
├── .github/workflows/ci.yml        ruff + mypy + pytest (cov gate 80) | hadolint (live replay: live-replay.yml, weekly)
├── Dockerfile                      mcr.microsoft.com/playwright/python:v1.65.1-noble + uv
├── Makefile                        install, test, e2e, demo, bench, report, catalog, docker
├── CHANGELOG.md  LICENSE  README.md  pyproject.toml  uv.lock  .env.example
├── src/llm_test_generator/
│   ├── cli.py            ltg run | report | stories | check | catalog show/capture
│   ├── pipeline.py       generate -> validate -> execute -> repair (max 2), attempts.json
│   ├── stories.py        Markdown user stories + Gherkin (Background, Scenario Outline)
│   ├── catalog.py        page catalog model, prompt rendering, nearest-id suggestions
│   ├── capture.py        Playwright tour of saucedemo.com that captures the catalog
│   ├── catalogs/saucedemo.json   15 page states, 99 data-test ids (committed)
│   ├── validate.py       static checks: structure, imports, sleeps, catalog ids, ruff
│   ├── executor.py       isolated pytest-playwright subprocess, JUnit, failure classes
│   ├── prompts.py        system/generation/repair prompts, PROMPT_VERSION
│   ├── providers.py      Ollama (default), Anthropic, OpenAI (lazy extras), fake
│   ├── report.py         run summaries and comparison tables
│   ├── config.py  models.py  __main__.py
├── tests/                106 unit tests + tests/e2e (live site, live LLM; deselected by default)
├── examples/stories/     12 stories: 2 Markdown files, 2 .feature files
├── examples/generated/   the 8 tests qwen3:8b generated that pass (unedited, replayed weekly by live-replay.yml)
└── docs/
    ├── REPO-META.md      description (115 chars) + 10 topics
    ├── BUILD-REPORT.md   this file
    └── results/          pytest.txt, lint.txt, e2e-replay.txt, report.md, sample prompt,
                          benchmark/<run>/ (attempts.json, every answer, test and pytest output)
```

## Tests and coverage

- `uv run pytest`: **106 passed**, 10 deselected (e2e / live), **97.70 %** line + branch
  coverage (gate 80 %). Raw: `docs/results/pytest.txt`.
- `uv run ruff check .`, `uv run ruff format --check .`: clean. `uv run mypy` (strict): clean,
  14 files. Raw: `docs/results/lint.txt`.
- e2e (live saucedemo.com + Chromium): the 8 committed generated tests pass
  (`docs/results/e2e-replay.txt`); the catalog drift check passes (re-capture gives the same
  pages and ids).

## Demo command and output

```bash
LLM_SEED=42 uv run ltg run examples/stories --run-id qwen3-8b-think-off --out runs
```

Ollama `qwen3:8b`, thinking off, against the live saucedemo.com. Summary of the output (full
console in `docs/results/benchmark/qwen3-8b-think-off/console.txt` and pasted in the README):

```text
valid on 1st attempt: 8/12 (67 %); after repair 1: 8/12 (67 %); after repair 2: 8/12 (67 %)
LLM calls: 20, median latency 29.2 s, wall time 12.1 min
```

`make demo` runs a 3-story subset of the same command.

## Measured results

| Configuration | Valid on 1st attempt | After 2 repairs | LLM calls | Median LLM latency |
|---|---|---|---|---|
| qwen3:8b, thinking off | 8/12 (67 %) | 8/12 (67 %) | 20 | 29.2 s |
| qwen3:8b, thinking on | to be measured (1/12 done, passed, 179 s per generation) | | | |

- The repair loop recovered **0 of 4** failures. All four were wrong assumptions about the app
  that the model repeated after seeing the error: a `/login.html` URL, a container expected to
  disappear, an exact text on a two-element locator (then a non-existent `exact=` argument), and
  `.first()` called on the assertion instead of the locator. Details are in the README Results
  section and `docs/results/report.md`.
- All 8 passing tests assert their acceptance criteria. I read them, and the checkout test
  checks the URL of every step, both totals and the confirmation heading.

## Problems found during the build (fixed, with evidence kept)

1. With a relative `--out`, pytest ran with `cwd=run_dir` and resolved paths twice, so every
   test failed to collect. Fixed (`d6c3fb1`) and covered by a regression test. That run was
   discarded and not kept.
2. The first catalog captured only the backpack's remove button. The validator then rejected
   the valid `remove-sauce-labs-bike-light`. The capture now fills the cart (`7c289e0`).
   Run kept as `docs/results/benchmark/aborted-1-catalog-gap/`.
3. The shared Ollama returned HTTP 500 "token repeat limit reached" for all 12 stories within
   2–4 s retries, and the same prompts succeeded minutes later. Fixes: `presence_penalty` 1.5
   (Qwen3 recommendation, `f12c5cf`) and exponential backoff with 4 retries (`9f4d325`). Run
   kept as `aborted-2-shared-server-http500/`.
4. num_ctx was agreed with the orchestrator session: both clients send `num_ctx=16384`, so
   Ollama does not reload qwen3:8b between sessions.

## Known limitations

- One app, 12 stories, one seed. These numbers describe this setup, not model quality in
  general.
- Only one local chat model (qwen3:8b). Hosted providers are implemented and unit-tested
  against fake clients, but not measured.
- The catalog tour is specific to saucedemo.com. `get_by_role` / `get_by_text` selectors and
  f-string ids are not checked against it.
- "Valid" means the test passes. Whether every acceptance criterion is asserted was checked by
  reading the tests, not automatically.
- saucedemo.com is third-party. The scheduled live-replay workflow will flag drift.
- Generated code runs unsandboxed on the host; the validator is not a security boundary
  (README, Limitations).

## Not done

- **Thinking-on benchmark:** Claude Code stopped the run after 1/12 stories because the
  machine was low on memory. I did not restart it, as instructed by that notice. To reproduce:
  `LLM_SEED=42 uv run ltg run examples/stories --run-id qwen3-8b-think-on --think`.
- **Dockerfile:** not built, because the Docker daemon is off, and not linted locally, because
  the hadolint binary download was denied by the permission classifier. The CI `dockerfile`
  job runs hadolint.
- **CI:** never executed, since there is no remote. The workflow YAML was not run on GitHub.
- **Hosted model runs** (Anthropic / OpenAI): no API keys were used.
