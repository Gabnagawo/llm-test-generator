# llm-test-generator: user stories -> executed, self-corrected Playwright tests.
#
#   docker build -t llm-test-generator .
#   # Ollama on the host:
#   docker run --rm -e OLLAMA_HOST=http://host.docker.internal:11434 \
#     -v "$PWD/runs:/app/runs" llm-test-generator run examples/stories
# Same Playwright version as uv.lock, so the image's preinstalled Chromium matches.
FROM mcr.microsoft.com/playwright/python:v1.65.1-noble

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY examples ./examples
RUN uv sync --locked --no-dev && chown -R pwuser:pwuser /app

USER pwuser
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["ltg"]
CMD ["--help"]
