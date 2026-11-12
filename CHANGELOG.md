# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-12

### Added
- `ltg run`: turns user stories into Playwright (Python, sync API) tests with an LLM, runs each
  test against the live app in Chromium and sends failures back to the LLM with the error, up
  to 2 repairs per story (`--max-repairs`).
- Story parsers for Markdown user stories (`## title` + acceptance-criteria bullets) and Gherkin
  (`Scenario`, `Background`, `Scenario Outline` with `Examples`).
- Page catalog of saucedemo.com captured with Playwright across 13 page states (92 `data-test`
  ids, error messages, select options, repeated-element texts) and committed to the repo;
  `ltg catalog capture` re-captures it and an e2e test fails when the live site drifts.
- Static validation before any browser run: code extraction, syntax, test name and `page`
  fixture, at least one `expect` assertion, import allowlist, no sleeps / `evaluate` / external
  navigation, every `data-test` id checked against the catalog with nearest-id hints, and
  pyflakes-level lint through ruff.
- Isolated execution: each test runs in its own pytest subprocess with a generated `pytest.ini`
  and `conftest.py` (test id attribute, 5 s action timeouts), JUnit parsing and 12 failure
  categories (locator timeout, strict-mode violation, assertion, navigation, ...).
- Attempt log (`attempts.json`) with every prompt, answer, test file and pytest output, and
  `ltg report` comparing runs: valid on the first attempt vs after each repair, per model.
- Providers selected by `LLM_PROVIDER` / `LLM_MODEL`: Ollama (default `qwen3:8b`, `num_ctx`
  16384, Qwen3-recommended sampling, retries with a new seed), Anthropic and OpenAI as optional
  lazy extras, and a scripted fake provider for tests.
- `ltg check` (static validation of any test file) and `ltg stories`.
- Twelve example stories for saucedemo.com and the passing generated tests from the benchmark
  run in `examples/generated/`.
- CI (ruff, mypy, pytest with coverage gate, e2e replay of the generated tests on the live
  site, hadolint), Dockerfile on the Playwright 1.65.1 image and Makefile.

[0.1.0]: https://github.com/Gabnagawo/llm-test-generator/releases/tag/v0.1.0
