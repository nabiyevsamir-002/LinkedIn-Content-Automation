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
        # Hekayənin anlaşılması — şəkil axtarışından ƏVVƏL (15.09.2026)
        "story": {
            "type": "object",
            "properties": {
                "kind": _STR,
                "people": {"type": "array", "items": _STR},
                "organizations": {"type": "array", "items": _STR},
                "products": {"type": "array", "items": _STR},
                "action": _STR,
                "event": {
                    "type": "object",
                    "properties": {"name": _STR, "location": _STR, "date": _STR,
                                   "confirmed": {"type": "boolean"}},
                },
                "must_show": _STR,
                "irrelevant": {"type": "array", "items": _STR},
            },
            "required": ["kind", "people", "organizations", "action", "must_show",
                         "irrelevant"],
        },
    },
    "required": ["visual_type", "headline", "alt_text", "design_brief",
                 "photo_queries", "story"],
}

DESIGN = {
    "type": "object",
    "properties": {"html": _STR, "palette": _STR, "notes": _STR},
    "required": ["html"],
}
