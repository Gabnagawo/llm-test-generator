"""Parse user stories from Markdown and scenarios from Gherkin into :class:`Story` objects.

Markdown format (one story per ``##`` section)::

    ## Successful login
    Tags: @smoke @auth
    As a shopper, I want to log in so that I can see the products.

    ### Acceptance criteria
    - Given I am on the login page ...
    - Then I see the "Products" title

Gherkin: every ``Scenario`` is one story; ``Background`` steps are prepended and each
``Scenario Outline`` example row becomes its own story.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from llm_test_generator.models import Story, StoryFormat

STORY_SUFFIXES = {".md": StoryFormat.MARKDOWN, ".feature": StoryFormat.GHERKIN}

_STEP_RE = re.compile(r"^(Given|When|Then|And|But|\*)\s+(.+)$")
_TAG_RE = re.compile(r"@([\w-]+)")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
_CRITERIA_HEADINGS = ("acceptance criteria", "criteria", "acceptance")
_SCENARIO_KEYWORDS = {"scenario", "example", "scenario outline", "scenario template"}


class StoryParseError(ValueError):
    """Raised when a story file cannot be turned into at least one testable story."""


def slugify(text: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "-", text).strip("-").lower()
    return slug or "story"


def parse_markdown(text: str, source: str = "<string>") -> list[Story]:
    stories: list[Story] = []
    for title, body in _markdown_sections(text):
        tags: list[str] = []
        narrative: list[str] = []
        criteria: list[str] = []
        explicit_id: str | None = None
        in_criteria = False
        for raw in body:
            line = raw.strip()
            if not line:
                continue
            lower = line.lower()
            if line.startswith("#"):
                heading = line.lstrip("#").strip().lower()
                in_criteria = heading.startswith(_CRITERIA_HEADINGS)
                continue
            if lower.startswith("tags:"):
                tags.extend(_TAG_RE.findall(line))
                continue
            if lower.startswith("id:"):
                explicit_id = slugify(line.split(":", 1)[1])
                continue
            bullet = _BULLET_RE.match(raw)
            if in_criteria and bullet:
                criteria.append(bullet.group(1).strip())
            elif in_criteria and criteria:
                criteria[-1] += " " + line  # wrapped bullet
            else:
                narrative.append(line)
        if not criteria:
            raise StoryParseError(f"{source}: story {title!r} has no acceptance criteria bullets")
        stories.append(
            Story(
                id=explicit_id or slugify(title),
                title=title,
                narrative=" ".join(narrative),
                criteria=criteria,
                source=source,
                format=StoryFormat.MARKDOWN,
                tags=tags,
            )
        )
    if not stories:
        raise StoryParseError(f"{source}: no '## <title>' story sections found")
    return stories


def _markdown_sections(text: str) -> Iterable[tuple[str, list[str]]]:
    title: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if title is not None:
                yield title, body
            title, body = line[3:].strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        yield title, body


@dataclass
class _Scenario:
    title: str
    tags: list[str]
    outline: bool
    steps: list[str] = field(default_factory=list)
    examples: list[list[str]] = field(default_factory=list)


def parse_gherkin(text: str, source: str = "<string>") -> list[Story]:
    feature = ""
    feature_desc: list[str] = []
    feature_tags: list[str] = []
    background: list[str] = []
    pending_tags: list[str] = []
    scenarios: list[_Scenario] = []
    section = "preamble"

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            pending_tags.extend(_TAG_RE.findall(line))
            continue
        keyword, _, rest = line.partition(":")
        keyword = keyword.strip().lower()
        if keyword == "feature":
            feature, feature_tags, pending_tags = rest.strip(), pending_tags, []
            section = "feature"
        elif keyword == "background":
            section = "background"
        elif keyword in _SCENARIO_KEYWORDS:
            outline = keyword in {"scenario outline", "scenario template"}
            scenarios.append(_Scenario(rest.strip(), pending_tags, outline))
            pending_tags = []
            section = "scenario"
        elif keyword in {"examples", "scenarios"}:
            section = "examples"
        elif section == "examples" and line.startswith("|") and scenarios:
            scenarios[-1].examples.append([c.strip() for c in line.strip("|").split("|")])
        elif _STEP_RE.match(line):
            if section == "background":
                background.append(line)
            elif section == "scenario" and scenarios:
                scenarios[-1].steps.append(line)
        elif section == "feature":
            feature_desc.append(line)

    narrative = " ".join([f"Feature: {feature}", *feature_desc]).strip()
    stories: list[Story] = []
    for sc in scenarios:
        steps = [*background, *sc.steps]
        if not sc.steps:
            raise StoryParseError(f"{source}: scenario {sc.title!r} has no steps")
        variants: list[tuple[str, list[str]]] = [(sc.title, steps)]
        if sc.outline:
            if len(sc.examples) < 2:
                raise StoryParseError(f"{source}: outline {sc.title!r} needs an Examples table")
            header, *rows = sc.examples
            variants = []
            for n, row in enumerate(rows, start=1):
                mapping = dict(zip(header, row, strict=False))
                variants.append(
                    (f"{_fill(sc.title, mapping)} #{n}", [_fill(s, mapping) for s in steps])
                )
        stories.extend(
            Story(
                id=slugify(title),
                title=title,
                narrative=narrative,
                criteria=variant_steps,
                source=source,
                format=StoryFormat.GHERKIN,
                tags=[*feature_tags, *sc.tags],
            )
            for title, variant_steps in variants
        )
    if not stories:
        raise StoryParseError(f"{source}: no Scenario found")
    return stories


def _fill(template: str, mapping: dict[str, str]) -> str:
    return re.sub(r"<([^<>]+)>", lambda m: mapping.get(m.group(1), m.group(0)), template)


def load_stories(paths: Iterable[Path | str]) -> list[Story]:
    """Load every story from files and directories (``*.md`` and ``*.feature``, sorted)."""
    files: list[Path] = []
    for item in paths:
        path = Path(item)
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.suffix in STORY_SUFFIXES))
        elif path.suffix in STORY_SUFFIXES:
            files.append(path)
        else:
            raise StoryParseError(f"{path}: expected a .md or .feature file, or a directory")
    stories: list[Story] = []
    seen: set[str] = set()
    for file in files:
        text = file.read_text(encoding="utf-8")
        source = file.as_posix()
        parsed = (
            parse_gherkin(text, source)
            if STORY_SUFFIXES[file.suffix] is StoryFormat.GHERKIN
            else parse_markdown(text, source)
        )
        for story in parsed:
            if story.id in seen:
                raise StoryParseError(f"{source}: duplicate story id {story.id!r}")
            seen.add(story.id)
            stories.append(story)
    if not stories:
        raise StoryParseError("no stories found")
    return stories
