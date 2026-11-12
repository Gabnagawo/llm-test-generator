"""The page catalog: selectors captured from the live app, committed to the repo.

The LLM never sees the DOM. It sees this catalog, and the static validator rejects
any ``data-test`` id that is not in it, so a hallucinated selector fails before a
browser is started and the repair prompt can name the valid alternatives.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from importlib import resources
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CATALOG_SCHEMA_VERSION = 1
DEFAULT_CATALOG = "saucedemo"


class Element(BaseModel):
    """One element addressable through its ``data-test`` attribute."""

    model_config = ConfigDict(frozen=True)

    test_id: str
    tag: str
    count: int = Field(default=1, ge=1, description="How many elements share this test id.")
    text: str = Field(default="", description="Visible text sample, trimmed.")
    input_type: str | None = None
    placeholder: str | None = None
    options: list[str] = Field(
        default_factory=list, description="<option> values, for <select> elements."
    )
    samples: list[str] = Field(
        default_factory=list, description="Distinct texts of repeated elements, in DOM order."
    )

    def describe(self) -> str:
        parts = [f'"{self.test_id}"', self.tag]
        if self.input_type:
            parts.append(f"type={self.input_type}")
        if self.placeholder:
            parts.append(f"placeholder={self.placeholder!r}")
        if self.count > 1:
            parts.append(f"x{self.count} (use .first / .nth(i) / filter)")
        if self.options:
            parts.append("options=" + ",".join(self.options))
        if self.samples and len(self.samples) > 1:
            parts.append(
                "distinct texts in page order=" + json.dumps(self.samples, ensure_ascii=False)
            )
        elif self.text:
            parts.append(f"text={self.text!r}")
        return " ".join(parts)


class Page(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    state: str = Field(default="", description="How the page was reached during capture.")
    title: str = ""
    elements: list[Element]


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = CATALOG_SCHEMA_VERSION
    app: str
    base_url: str
    captured_at: datetime
    captured_with: str = ""
    test_id_attribute: str = "data-test"
    credentials: dict[str, str] = Field(
        default_factory=dict, description="Public demo accounts printed on the login page."
    )
    notes: list[str] = Field(default_factory=list)
    pages: list[Page]

    @property
    def test_ids(self) -> frozenset[str]:
        return frozenset(e.test_id for p in self.pages for e in p.elements)

    def page(self, name: str) -> Page:
        for page in self.pages:
            if page.name == name:
                return page
        raise KeyError(name)

    def render(self) -> str:
        """Compact text form of the catalog for the prompt."""
        lines = [
            f"App: {self.app} at {self.base_url}",
            f"Test id attribute: {self.test_id_attribute} "
            f'(the fixture is configured so page.get_by_test_id("x") matches '
            f'[{self.test_id_attribute}="x"])',
        ]
        if self.credentials:
            accounts = ", ".join(f"{u} / {p}" for u, p in self.credentials.items())
            lines.append(f"Demo accounts (username / password): {accounts}")
        lines.extend(f"Note: {note}" for note in self.notes)
        seen: dict[str, str] = {}
        for page in self.pages:
            header = f"\n## page {page.name}: {page.path}"
            if page.state:
                header += f"  ({page.state})"
            lines.append(header)
            # Header, menu and footer repeat on every page; describe each id in full where
            # it first appears (or where its text changes) and only name it afterwards.
            shared = []
            for element in page.elements:
                if seen.get(element.test_id) == element.text:
                    shared.append(element.test_id)
                else:
                    lines.append(f"- {element.describe()}")
                seen[element.test_id] = element.text
            if shared:
                lines.append("- also present (described above): " + ", ".join(shared))
        return "\n".join(lines)

    def suggest(self, test_id: str, limit: int = 5) -> list[str]:
        """Known test ids that look closest to an unknown one (for repair prompts)."""
        from difflib import get_close_matches

        return get_close_matches(test_id, sorted(self.test_ids), n=limit, cutoff=0.4)

    def sha256(self) -> str:
        payload = self.model_dump_json(exclude={"captured_at"}).encode()
        return hashlib.sha256(payload).hexdigest()


def load_catalog(name_or_path: str | Path = DEFAULT_CATALOG) -> Catalog:
    """Load a bundled catalog by name (``saucedemo``) or any catalog JSON file by path."""
    path = Path(name_or_path)
    if path.suffix == ".json" or path.exists():
        return Catalog.model_validate_json(path.read_text(encoding="utf-8"))
    bundled = resources.files("llm_test_generator").joinpath(f"catalogs/{name_or_path}.json")
    if not bundled.is_file():
        raise FileNotFoundError(f"no bundled catalog named {name_or_path!r}")
    return Catalog.model_validate_json(bundled.read_text(encoding="utf-8"))


def dump_catalog(catalog: Catalog, path: Path) -> None:
    data = json.loads(catalog.model_dump_json())
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
