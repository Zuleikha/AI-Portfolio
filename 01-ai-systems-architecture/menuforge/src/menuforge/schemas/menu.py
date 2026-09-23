"""ExtractedMenu and MenuItemSchema — the validation contract.

Single source of truth for what a valid extracted menu is. Used both to validate
the model's tool arguments and to shape the API response, so the two cannot drift.

The JSON schema handed to Claude in `menuforge.llm.client` describes the same
shape and is kept in sync by hand — change them together.
"""

from pydantic import BaseModel, Field


class MenuItemSchema(BaseModel):
    """One item on a menu.

    `name` and `price` are required — an item without them is not usable data and
    is what the retry loop in `menuforge.llm.client` exists to recover from.
    `description` and `modifiers` default, because plenty of menus omit them.
    """

    name: str
    price: float
    description: str = ""
    modifiers: list[str] = Field(default_factory=list)


class ExtractedMenu(BaseModel):
    """Every item found in one menu image.

    An empty `items` list is valid: the model may legitimately find no items in
    an image that is not a menu. Validation proves shape, not correctness.
    """

    items: list[MenuItemSchema]
