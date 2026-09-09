"""Vizual agentlərin JSON sxemləri."""
from __future__ import annotations

_STR = {"type": "string"}

DIRECTOR = {
    "type": "object",
    "properties": {
        "visual_type": _STR, "chart_style": _STR, "reasoning": _STR, "kicker": _STR,
        "headline": _STR, "support": _STR,
        "data_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": _STR, "value": _STR, "unit": _STR,
                    "numeric": {"type": "number"},
                    "highlight": {"type": "boolean"},
                },
                "required": ["label", "value", "numeric"],
            },
        },
        "pexels_query": _STR,                       # köhnə sahə (uyğunluq üçün)
        "photo_queries": {"type": "array", "items": _STR},
        "design_brief": _STR, "alt_text": _STR,
        "accent_words": {"type": "array", "items": _STR},
    },
    "required": ["visual_type", "headline", "alt_text", "design_brief",
                 "photo_queries"],
}

DESIGN = {
    "type": "object",
    "properties": {"html": _STR, "palette": _STR, "notes": _STR},
    "required": ["html"],
}
