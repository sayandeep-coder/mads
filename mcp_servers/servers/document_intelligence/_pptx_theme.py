from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.util import Pt

# Slide canvas: standard 16:9 widescreen (10" x 5.625")
SLIDE_WIDTH_IN = 10.0
SLIDE_HEIGHT_IN = 5.625

INK = RGBColor(0x1A, 0x1A, 0x2E)  # near-black, for body/heading text
MUTED = RGBColor(0x6B, 0x72, 0x80)  # slate gray, for secondary text
LIGHT_BG = RGBColor(0xFA, 0xFA, 0xFC)  # off-white background
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT_FAMILY = "Calibri"

TITLE_SIZE = Pt(40)
SECTION_TITLE_SIZE = Pt(36)
SLIDE_TITLE_SIZE = Pt(28)
SUBTITLE_SIZE = Pt(18)
BODY_SIZE = Pt(16)
CAPTION_SIZE = Pt(12)


def accent_color(hex_color: str | None) -> RGBColor:
    """Parse a '#RRGGBB' string into an RGBColor, falling back to a professional default blue."""
    if not hex_color:
        return RGBColor(0x2D, 0x5B, 0xFF)

    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return RGBColor(0x2D, 0x5B, 0xFF)

    try:
        return RGBColor(int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    except ValueError:
        return RGBColor(0x2D, 0x5B, 0xFF)
