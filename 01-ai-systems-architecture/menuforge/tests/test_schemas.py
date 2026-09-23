"""Tests for the validation contract.

Pure unit tests — no mocks, no I/O. These pin the boundary the retry loop in
menuforge.llm.client is written against.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from menuforge.schemas import ExtractedMenu, MenuItemSchema


def test_optional_fields_default() -> None:
    item = MenuItemSchema.model_validate({"name": "Tea", "price": 2.0})

    assert item.description == ""
    assert item.modifiers == []


def test_modifiers_default_is_not_shared() -> None:
    """A mutable default must not be shared between instances."""
    first = MenuItemSchema(name="Tea", price=2.0)
    second = MenuItemSchema(name="Coffee", price=3.0)

    first.modifiers.append("oat milk")

    assert second.modifiers == []


def test_missing_price_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MenuItemSchema.model_validate({"name": "Pizza"})


def test_missing_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MenuItemSchema.model_validate({"price": 9.0})


def test_non_numeric_price_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MenuItemSchema.model_validate({"name": "Pizza", "price": "twelve fifty"})


def test_numeric_string_price_is_coerced() -> None:
    """Documents real behaviour: Pydantic coerces a numeric string to float."""
    item = MenuItemSchema.model_validate({"name": "Pizza", "price": "12.50"})

    assert item.price == 12.5


def test_integer_price_becomes_float() -> None:
    item = MenuItemSchema.model_validate({"name": "Tea", "price": 2})

    assert item.price == 2.0
    assert isinstance(item.price, float)


def test_empty_menu_is_valid() -> None:
    assert ExtractedMenu.model_validate({"items": []}).items == []


def test_missing_items_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExtractedMenu.model_validate({})


def test_one_bad_item_rejects_the_whole_menu() -> None:
    """All-or-nothing: a menu is not partially valid."""
    with pytest.raises(ValidationError):
        ExtractedMenu.model_validate({"items": [{"name": "Tea", "price": 2.0}, {"name": "Pizza"}]})
