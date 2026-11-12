"""``ltg``: generate, run and self-correct Playwright tests from user stories."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from llm_test_generator import __version__
from llm_test_generator.catalog import DEFAULT_CATALOG, dump_catalog, load_catalog
from llm_test_generator.config import Settings
from llm_test_generator.models import Attempt, AttemptOutcome, Story
from llm_test_generator.pipeline import Mode, Pipeline, PipelineConfig, Progress, new_run_id
from llm_test_generator.providers import build_provider
from llm_test_generator.report import load_run, render_markdown, summarize
from llm_test_generator.stories import StoryParseError, load_stories
from llm_test_generator.validate import validate

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Generate, run and self-correct Playwright tests from user stories.",
)
catalog_app = typer.Typer(no_args_is_help=True, help="Inspect or re-capture the page catalog.")
app.add_typer(catalog_app, name="catalog")

console = Console(highlight=False, soft_wrap=True)
DEFAULT_STORIES = [Path("examples/stories")]


def _version(value: bool) -> None:
    if value:
        console.print(f"llm-test-generator {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    """Generate, run and self-correct Playwright tests from user stories."""


def _load(paths: list[Path], only: list[str] | None) -> list[Story]:
    try:
        stories = load_stories(paths)
    except (StoryParseError, OSError) as exc:
        console.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(2) from exc
    if only:
        unknown = sorted(set(only) - {s.id for s in stories})
        if unknown:
            console.print(f"[red]error:[/red] unknown story id(s): {', '.join(unknown)}")
            raise typer.Exit(2)
        stories = [s for s in stories if s.id in only]
    return stories


def _progress(total: int) -> Progress:
    seen: dict[str, int] = {}

    def show(story: Story, attempt: Attempt) -> None:
        index = seen.setdefault(story.id, len(seen) + 1)
        latency = f"{attempt.llm.latency_s:.1f} s LLM" if attempt.llm else "no LLM answer"
        if attempt.execution:
            latency += f", {attempt.execution.duration_s:.1f} s browser"
        if attempt.outcome is AttemptOutcome.PASSED:
            outcome = "[green]PASS[/green]"
        else:
            outcome = f"[yellow]{attempt.outcome.value}[/yellow] {attempt.failure_category}"
            if attempt.failure_message:
                outcome += f": {escape(attempt.failure_message[:110])}"
        console.print(
            f"[{index:>2}/{total}] {story.id}  #{attempt.number} {attempt.kind.value:<8} "
            f"{outcome}  ({latency})"
        )

    return show


@app.command()
def run(
    stories: Annotated[
        list[Path] | None, typer.Argument(help="Story files or directories (.md, .feature).")
    ] = None,
    only: Annotated[list[str] | None, typer.Option("--only", help="Story id(s) to run.")] = None,
    catalog: Annotated[
        str, typer.Option(help="Bundled catalog name or JSON path.")
    ] = DEFAULT_CATALOG,
    out: Annotated[Path, typer.Option(help="Directory for run folders.")] = Path("runs"),
    run_id: Annotated[
        str | None, typer.Option(help="Run folder name (default: time+model).")
    ] = None,
    mode: Annotated[
        str, typer.Option(help="run: execute in Chromium; generate: static only.")
    ] = "run",
    max_repairs: Annotated[int | None, typer.Option(min=0, max=5)] = None,
    provider: Annotated[str | None, typer.Option(help="Overrides LLM_PROVIDER.")] = None,
    model: Annotated[str | None, typer.Option(help="Overrides LLM_MODEL.")] = None,
    think: Annotated[bool | None, typer.Option(help="Ollama thinking mode (OLLAMA_THINK).")] = None,
    seed: Annotated[int | None, typer.Option(help="Sampling seed (LLM_SEED).")] = None,
    base_url: Annotated[str | None, typer.Option(help="Overrides LTG_BASE_URL.")] = None,
    headed: Annotated[bool, typer.Option(help="Show the browser.")] = False,
) -> None:
    """Generate a test per story, run it, and repair failures with the error as feedback."""
    if mode not in ("run", "generate"):
        raise typer.BadParameter("mode must be 'run' or 'generate'", param_hint="--mode")
    overrides = {
        "llm_provider": provider,
        "llm_model": model,
        "ollama_think": think,
        "llm_seed": seed,
        "base_url": base_url,
        "max_repairs": max_repairs,
    }
    settings = Settings().model_copy(update={k: v for k, v in overrides.items() if v is not None})
    selected = _load(stories or DEFAULT_STORIES, only)
    try:
        llm = build_provider(settings)
    except ValueError as exc:
        console.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(2) from exc
    cat = load_catalog(catalog)
    run_dir = out / (run_id or new_run_id(llm.model))
    run_mode: Mode = "run" if mode == "run" else "generate"
    config = PipelineConfig(
        base_url=settings.base_url,
        max_repairs=settings.max_repairs,
        mode=run_mode,
        test_timeout_s=settings.test_timeout_s,
        headed=headed,
    )
    console.print(
        f"llm-test-generator {__version__}: {len(selected)} stories, {llm.name} {llm.model}, "
        f"mode={run_mode}, max repairs={config.max_repairs}, target {config.base_url}"
    )
    console.print(f"run folder: {run_dir.as_posix()}")
    pipeline = Pipeline(llm, cat, run_dir, config, progress=_progress(len(selected)))
    log = pipeline.run(selected)
    summary = summarize(log)
    console.print()
    console.print(
        f"valid on 1st attempt: {summary.rate(summary.passed_first)}; "
        + "; ".join(
            f"after repair {i}: {summary.rate(c)}"
            for i, c in enumerate(summary.passed_by_attempt[1:], start=1)
        )
    )
    console.print(
        f"LLM calls: {summary.llm_calls}, median latency {summary.median_llm_latency_s} s, "
        f"wall time {summary.total_wall_s / 60:.1f} min"
    )
    console.print(f"passing tests: {(run_dir / 'passing').as_posix()}/")
    console.print(f"attempt log:   {pipeline.log_path.as_posix()}")


@app.command()
def report(
    runs: Annotated[list[Path], typer.Argument(help="Run folders or attempts.json files.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write Markdown here.")
    ] = None,
) -> None:
    """Compare runs: valid tests on the first attempt vs after repair, per model."""
    text = render_markdown([load_run(p) for p in runs])
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline="\n")
        console.print(f"wrote {output.as_posix()}")
    else:
        sys.stdout.write(text)


@app.command("stories")
def list_stories(
    paths: Annotated[list[Path] | None, typer.Argument(help="Story files or directories.")] = None,
) -> None:
    """List the parsed stories and the test name each one gets."""
    for story in _load(paths or DEFAULT_STORIES, None):
        tags = " ".join(f"@{t}" for t in story.tags)
        console.print(f"{story.id:<58} {len(story.criteria)} criteria  {tags}")


@app.command()
def check(
    test_file: Annotated[Path, typer.Argument(help="A test file to validate statically.")],
    test_name: Annotated[str | None, typer.Option(help="Expected test function name.")] = None,
    catalog: Annotated[str, typer.Option()] = DEFAULT_CATALOG,
    base_url: Annotated[str, typer.Option()] = "https://www.saucedemo.com",
) -> None:
    """Run the static validator on an existing test file."""
    cat = load_catalog(catalog)
    name = test_name or test_file.stem
    result = validate(
        f"```python\n{test_file.read_text(encoding='utf-8')}\n```", name, cat, base_url
    )
    if result.ok:
        console.print(f"[green]ok[/green] {test_file.as_posix()}")
        return
    for issue in result.issues:
        console.print(f"{test_file.as_posix()}: {escape(issue.render())}")
    raise typer.Exit(1)


@catalog_app.command("show")
def catalog_show(name: Annotated[str, typer.Argument()] = DEFAULT_CATALOG) -> None:
    """Print the catalog exactly as the LLM sees it."""
    cat = load_catalog(name)
    sys.stdout.write(cat.render() + "\n")
    sys.stdout.write(
        f"\n{len(cat.pages)} page states, {len(cat.test_ids)} test ids, captured "
        f"{cat.captured_at.isoformat()} with {cat.captured_with}, sha256 {cat.sha256()[:12]}\n"
    )


@catalog_app.command("capture")
def catalog_capture(
    output: Annotated[Path, typer.Option("--output", "-o")] = Path(
        "src/llm_test_generator/catalogs/saucedemo.json"
    ),
    base_url: Annotated[str, typer.Option()] = "https://www.saucedemo.com",
    headed: Annotated[bool, typer.Option()] = False,
) -> None:  # pragma: no cover - needs a browser and network; see tests/e2e
    """Re-capture the saucedemo catalog from the live site with Playwright."""
    from llm_test_generator.capture import capture_catalog

    cat = capture_catalog(base_url, headless=not headed)
    dump_catalog(cat, output)
    console.print(f"wrote {output.as_posix()}: {len(cat.pages)} pages, {len(cat.test_ids)} ids")
