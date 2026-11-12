# Linux/macOS/CI. On Windows run the `uv run ...` commands shown in the README.
.PHONY: install browsers lint format typecheck test e2e demo bench report catalog docker clean

STORIES ?= examples/stories
MODEL ?= qwen3:8b

install:
	uv sync

browsers:
	uv run playwright install chromium

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest

# Live site + Chromium: committed generated tests and a catalog drift check.
e2e:
	uv run pytest -m e2e --no-cov -v

# Needs Ollama running locally with $(MODEL) pulled (or LLM_PROVIDER/LLM_MODEL set).
demo:
	uv run ltg run $(STORIES) --only successful-login --only sorting-by-price-from-low-to-high --only checkout-requires-a-first-name --model $(MODEL)

# The full benchmark: every story, generation + execution + up to 2 repairs.
bench:
	LLM_SEED=42 uv run ltg run $(STORIES) --model $(MODEL)

report:
	uv run ltg report runs/*/

catalog:
	uv run ltg catalog capture

docker:
	docker build -t llm-test-generator .

clean:
	rm -rf runs .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml htmlcov
