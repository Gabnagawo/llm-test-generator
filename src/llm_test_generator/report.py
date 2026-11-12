"""Summaries of one or more attempt logs: first-attempt vs after-repair validity per model."""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from llm_test_generator.models import AttemptOutcome, FinalStatus, RunLog


class RunSummary(BaseModel):
    run_id: str
    mode: str
    provider: str
    model: str
    think: bool | None
    stories: int
    passed_first: int
    passed_by_attempt: list[int]
    """Cumulative passes after attempt 1, 2, ... (index 0 = first attempt)."""
    failed: int
    llm_calls: int
    provider_errors: int
    static_rejections: int
    execution_failures: int
    median_llm_latency_s: float | None
    total_llm_s: float
    total_wall_s: float
    first_attempt_failures: dict[str, int]
    all_failures: dict[str, int]

    @property
    def passed_final(self) -> int:
        return self.passed_by_attempt[-1] if self.passed_by_attempt else 0

    def rate(self, count: int) -> str:
        return (
            f"{count}/{self.stories} ({100 * count / self.stories:.0f} %)" if self.stories else "-"
        )

    @property
    def label(self) -> str:
        if self.think is None:
            return f"{self.provider} {self.model}"
        return f"{self.provider} {self.model} (think={'on' if self.think else 'off'})"


def load_run(path: Path) -> RunLog:
    file = path / "attempts.json" if path.is_dir() else path
    return RunLog.model_validate_json(file.read_text(encoding="utf-8"))


def summarize(log: RunLog) -> RunSummary:
    max_attempts = log.meta.max_repairs + 1
    passed_at = Counter(len(r.attempts) for r in log.results if r.passed)
    cumulative, running = [], 0
    for n in range(1, max_attempts + 1):
        running += passed_at.get(n, 0)
        cumulative.append(running)
    attempts = [a for r in log.results for a in r.attempts]
    latencies = [a.llm.latency_s for a in attempts if a.llm]
    first_failures = Counter(
        r.attempts[0].failure_category.value
        for r in log.results
        if r.attempts and r.attempts[0].failure_category
    )
    all_failures = Counter(a.failure_category.value for a in attempts if a.failure_category)
    think = log.meta.options.get("think")
    return RunSummary(
        run_id=log.meta.run_id,
        mode=log.meta.mode,
        provider=log.meta.provider,
        model=log.meta.model,
        think=think if isinstance(think, bool) else None,
        stories=len(log.results),
        passed_first=sum(r.final_status is FinalStatus.PASSED_FIRST_ATTEMPT for r in log.results),
        passed_by_attempt=cumulative,
        failed=sum(not r.passed for r in log.results),
        llm_calls=len(latencies),
        provider_errors=sum(a.outcome is AttemptOutcome.PROVIDER_ERROR for a in attempts),
        static_rejections=sum(a.outcome is AttemptOutcome.STATIC_FAILED for a in attempts),
        execution_failures=sum(a.outcome is AttemptOutcome.EXECUTION_FAILED for a in attempts),
        median_llm_latency_s=round(statistics.median(latencies), 1) if latencies else None,
        total_llm_s=round(sum(latencies), 1),
        total_wall_s=round(sum(r.duration_s for r in log.results), 1),
        first_attempt_failures=dict(first_failures.most_common()),
        all_failures=dict(all_failures.most_common()),
    )


def comparison_table(summaries: list[RunSummary]) -> str:
    """One row per run: the headline numbers of the benchmark."""
    max_attempts = max((len(s.passed_by_attempt) for s in summaries), default=1)
    repair_cols = [f"after repair {i}" for i in range(1, max_attempts)]
    header = [
        "model",
        "stories",
        "valid on 1st attempt",
        *repair_cols,
        "failed",
        "LLM calls",
        "median LLM latency",
        "wall time",
    ]
    rows = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for s in summaries:
        cumul = [s.rate(c) for c in s.passed_by_attempt[1:]]
        cumul += ["-"] * (len(repair_cols) - len(cumul))
        rows.append(
            "| "
            + " | ".join(
                [
                    s.label,
                    str(s.stories),
                    s.rate(s.passed_first),
                    *cumul,
                    str(s.failed),
                    str(s.llm_calls),
                    f"{s.median_llm_latency_s} s" if s.median_llm_latency_s is not None else "-",
                    f"{s.total_wall_s / 60:.1f} min",
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def story_table(log: RunLog) -> str:
    rows = ["| story | attempts | result | attempt outcomes |", "|---|---|---|---|"]
    for r in log.results:
        outcomes = " -> ".join(
            "pass" if a.outcome is AttemptOutcome.PASSED else (a.failure_category or "fail")
            for a in r.attempts
        )
        rows.append(f"| {r.story.id} | {len(r.attempts)} | {r.final_status.value} | {outcomes} |")
    return "\n".join(rows)


def render_markdown(logs: list[RunLog]) -> str:
    summaries = [summarize(log) for log in logs]
    parts = ["## Comparison", "", comparison_table(summaries)]
    for log, s in zip(logs, summaries, strict=True):
        valid = "passed against the live app" if s.mode == "run" else "passed static validation"
        parts += [
            "",
            f"## {s.label} - run `{s.run_id}`",
            "",
            f"Mode `{s.mode}`: a test counts as valid when it {valid}. "
            f"Prompt version `{log.meta.prompt_version}`, max repairs {log.meta.max_repairs}.",
            "",
            f"- LLM calls: {s.llm_calls} (provider errors: {s.provider_errors}), "
            f"static rejections: {s.static_rejections}, execution failures: "
            f"{s.execution_failures}",
            f"- First-attempt failure categories: {_fmt_counts(s.first_attempt_failures)}",
            f"- All failure categories: {_fmt_counts(s.all_failures)}",
            "",
            story_table(log),
        ]
    return "\n".join(parts) + "\n"


def _fmt_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "none"
