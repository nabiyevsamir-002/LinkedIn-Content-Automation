"""Agent çıxışları üçün JSON sxemləri.

`--json-schema` bayrağı modelə strukturu məcbur edir — bu, "cavabdan JSON
çıxarıla bilmədi" sinifindən olan bütün kövrəkliyi aradan qaldırır.
"""
from __future__ import annotations

_STR = {"type": "string"}
_INT = {"type": "integer"}


def _arr(items):
    return {"type": "array", "items": items}


SCOUT = {
    "type": "object",
    "properties": {
        "candidates": _arr({
            "type": "object",
            "properties": {
                "cluster_id": _INT, "title": _STR, "hook": _STR, "pillar": _STR,
                "why": _STR, "local_angle_potential": _STR, "score": _INT,
                # Məcburi deyil: həqiqi dəyər klasterdən götürülür
                # (`pipeline._enrich`), bu sahə yalnız modelin öz
                # balansını izləməsi üçündür.
                "region": _STR,
            },
            "required": ["cluster_id", "title", "hook", "pillar", "why", "score"],
        }),
        "skip_reason": {"type": ["string", "null"]},
    },
    "required": ["candidates"],
}

RESEARCHER = {
    "type": "object",
    "properties": {
        "headline": _STR, "primary_source_url": _STR, "summary": _STR,
        "facts": _arr({
            "type": "object",
            "properties": {"claim": _STR, "source_url": _STR, "confidence": _STR},
            "required": ["claim", "confidence"],
        }),
        "numbers": _arr({
            "type": "object",
            "properties": {"label": _STR, "value": _STR, "source_url": _STR},
            "required": ["label", "value"],
        }),
        "quotes": _arr({
            "type": "object",
            "properties": {"text": _STR, "speaker": _STR, "source_url": _STR},
            "required": ["text"],
        }),
        "context": _STR, "contrarian_note": _STR, "open_questions": _arr(_STR),
    },
    "required": ["headline", "summary", "facts"],
}

WRITER = {
    "type": "object",
    "properties": {
        "angles": _arr({
            "type": "object",
            "properties": {
                "id": _INT, "type": _STR, "headline": _STR,
                "thesis": _STR, "strength": _INT, "risk": _STR,
            },
            "required": ["id", "type", "headline", "thesis", "strength"],
        }),
        "chosen_angle_id": _INT, "why_chosen": _STR, "post": _STR,
        "thesis": _STR, "first_comment": _STR, "hashtags": _arr(_STR),
    },
    "required": ["angles", "chosen_angle_id", "post", "thesis", "first_comment"],
}

REVIEWER = {
    "type": "object",
    "properties": {
        "fact_check": {
            "type": "object",
            "properties": {
                "verdict": _STR,
                "issues": _arr({
                    "type": "object",
                    "properties": {"claim": _STR, "problem": _STR, "severity": _STR},
                    "required": ["problem", "severity"],
                }),
            },
            "required": ["verdict", "issues"],
        },
        "skeptic": {
            "type": "object",
            "properties": {
                "stop_scroll": _INT, "would_comment": {"type": "boolean"},
                "cringe": _arr(_STR), "verdict": _STR,
            },
            "required": ["stop_scroll", "would_comment", "verdict"],
        },
        "risk": {
            "type": "object",
            "properties": {"issues": _arr(_STR), "verdict": _STR},
            "required": ["issues", "verdict"],
        },
        "scores": {
            "type": "object",
            "properties": {
                "hook": _INT, "concreteness": _INT, "local_relevance": _INT,
                "voice": _INT, "scannability": _INT, "overall": _INT,
            },
            "required": ["hook", "concreteness", "local_relevance", "voice", "overall"],
        },
        "must_fix": _arr(_STR),
        "publish_recommendation": _STR,
    },
    "required": ["fact_check", "skeptic", "risk", "scores", "must_fix",
                 "publish_recommendation"],
}

REVISER = {
    "type": "object",
    "properties": {
        "post": _STR, "first_comment": _STR, "changes": _arr(_STR),
        "rejected_fixes": _arr({
            "type": "object",
            "properties": {"fix": _STR, "why_rejected": _STR},
            "required": ["fix", "why_rejected"],
        }),
        "voice_preserved": {"type": "boolean"}, "voice_note": _STR,
    },
    "required": ["post", "first_comment", "changes", "voice_preserved"],
}
