"""Regenerate `sample_menu.png`, the fixture the live extraction test sends.

Run manually — the PNG is committed, so this is not executed by the suite:

    python tests/fixtures/generate_menu_image.py

The menu is entirely invented. Nothing here belongs to a real business, so the
fixture can be committed and shared without any question about its provenance.

Uses Pillow's bundled default font at an explicit size rather than a system
TrueType file, so the output is identical on Windows, macOS and Linux.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path(__file__).resolve().parent / "sample_menu.png"

WIDTH, HEIGHT = 700, 900
MARGIN = 50
BACKGROUND = "white"
INK = "black"

# (kind, text) — kind picks the font and spacing below.
LINES: list[tuple[str, str]] = [
    ("title", "THE TEST KITCHEN"),
    ("subtitle", "sample menu"),
    ("gap", ""),
    ("section", "STARTERS"),
    ("item", "Tomato Soup                          4.50"),
    ("note", "slow-roasted tomato, fresh basil"),
    ("item", "Garlic Bread                         3.25"),
    ("note", "add cheese / add chilli flakes"),
    ("gap", ""),
    ("section", "MAINS"),
    ("item", "Margherita Pizza                    12.50"),
    ("note", "tomato, mozzarella, basil"),
    ("note", "add mushrooms / extra cheese"),
    ("item", "Mushroom Risotto                    11.00"),
    ("note", "arborio rice, parmesan, thyme"),
    ("gap", ""),
    ("section", "DRINKS"),
    ("item", "Espresso                             2.80"),
    ("item", "Orange Juice                         3.00"),
    ("note", "freshly squeezed"),
]

SIZES = {"title": 34, "subtitle": 20, "section": 24, "item": 22, "note": 16}
SPACING = {"title": 52, "subtitle": 46, "section": 40, "item": 32, "note": 26, "gap": 20}
INDENT = {"note": 30}


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    fonts = {kind: ImageFont.load_default(size=size) for kind, size in SIZES.items()}

    y = MARGIN
    for kind, text in LINES:
        if kind == "gap":
            y += SPACING["gap"]
            continue
        draw.text((MARGIN + INDENT.get(kind, 0), y), text, fill=INK, font=fonts[kind])
        y += SPACING[kind]

    # A rule under the header, so the layout reads as a menu rather than a list.
    # Sits below the subtitle baseline: title 50 + 52, subtitle + 46 => 148.
    draw.line([(MARGIN, 138), (WIDTH - MARGIN, 138)], fill=INK, width=2)

    image.save(OUTPUT, "PNG", optimize=True)
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
