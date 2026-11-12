from __future__ import annotations

from pathlib import Path

import pytest

from llm_test_generator.capture import normalize_elements
from llm_test_generator.catalog import Catalog, Element, dump_catalog, load_catalog


def test_bundled_catalog_covers_the_app(catalog: Catalog) -> None:
    names = [p.name for p in catalog.pages]
    assert names[0] == "login"
    assert {"inventory", "cart", "checkout_step_two", "checkout_complete"} <= set(names)
    assert {"username", "password", "login-button", "shopping-cart-badge", "finish"} <= (
        catalog.test_ids
    )
    assert catalog.test_id_attribute == "data-test"
    assert catalog.page("cart").path == "/cart.html"
    with pytest.raises(KeyError):
        catalog.page("nope")


def test_render_lists_each_id_once_unless_its_text_changes(catalog: Catalog) -> None:
    text = catalog.render()
    assert text.count('- "username" input') == 1
    assert "Sorry, this user has been locked out." in text
    assert "Error: First Name is required" in text
    assert "also present (described above)" in text
    assert "standard_user / secret_sauce" in text
    assert "options=az,za,lohi,hilo" in text


def test_suggest_close_ids(catalog: Catalog) -> None:
    assert catalog.suggest("user-name")[0] == "username"
    assert catalog.suggest("zzzzzzzz") == []


def test_sha_ignores_capture_time(catalog: Catalog) -> None:
    moved = catalog.model_copy(update={"captured_at": catalog.captured_at.replace(year=2001)})
    assert moved.sha256() == catalog.sha256()


def test_dump_and_load_roundtrip(catalog: Catalog, tmp_path: Path) -> None:
    path = tmp_path / "sub" / "cat.json"
    dump_catalog(catalog, path)
    assert b"\r\n" not in path.read_bytes()
    assert load_catalog(path) == catalog


def test_unknown_bundled_catalog() -> None:
    with pytest.raises(FileNotFoundError):
        load_catalog("todomvc")


def test_element_describe() -> None:
    element = Element(
        test_id="inventory-item-price", tag="div", count=6, samples=["$29.99", "$9.99"]
    )
    assert element.describe() == (
        '"inventory-item-price" div x6 (use .first / .nth(i) / filter) '
        'distinct texts in page order=["$29.99", "$9.99"]'
    )
    single = Element(test_id="username", tag="input", input_type="text", placeholder="Username")
    assert single.describe() == "\"username\" input type=text placeholder='Username'"


def test_normalize_elements_merges_repeats() -> None:
    rows = [
        {"test_id": "price", "tag": "div", "text": " $29.99 "},
        {"test_id": "price", "tag": "div", "text": "$9.99"},
        {"test_id": "price", "tag": "div", "text": "$9.99"},
        {"test_id": "", "tag": "div"},
        {"test_id": "sort", "tag": "select", "options": ["az", "za"], "text": ""},
        {"test_id": "user", "tag": "input", "input_type": "text", "placeholder": "Username"},
    ]
    price, sort, user = normalize_elements(rows)
    assert (price.count, price.text, price.samples) == (3, "$29.99", ["$29.99", "$9.99"])
    assert sort.options == ["az", "za"]
    assert sort.samples == []
    assert (user.input_type, user.placeholder) == ("text", "Username")
