"""Shared presentation constants for the command-line entry points.

Four modules each defined their own ``"=" * 78`` before Stage 15. The width is
arbitrary but it has to agree: the CLIs print banners around each other's
output, and two rules of different lengths in one terminal read as a mistake.
"""

from __future__ import annotations

RULE = "=" * 78
"""Horizontal rule printed around CLI banners. 78 columns fits an 80-column
terminal with room for a trailing newline."""
