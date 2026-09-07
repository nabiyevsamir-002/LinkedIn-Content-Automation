"""Postun Telegram-dan gələn əmrlə dəyişdirilməsi.

İki əməliyyat:
  apply_instruction — "tonu yumşalt, ikinci bəndi at" kimi sərbəst mətn
  rewrite           — başqa rakursla tamamilə yenidən yazmaq
"""
from __future__ import annotations

import json

from . import config, llm, schemas

EDITOR_SCHEMA = {
    "type": "object",
    "properties": {
        "post": {"type": "string"},
        "first_comment": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "string"}},
        "warning": {"type": "string"},
    },
    "required": ["post", "first_comment", "changes"],
}


def _prompt(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _voice() -> str:
    guide = (config.PROMPTS_DIR / "voice_guide.md").read_text(encoding="utf-8")
    pos = config.PROMPTS_DIR / "positioning.md"
    return guide + ("\n\n" + pos.read_text(encoding="utf-8") if pos.exists() else "")


def apply_instruction(post: str, first_comment: str, instruction: str,
                      agents: list | None = None) -> dict:
    payload = json.dumps({
        "post": post, "first_comment": first_comment,
        "user_instruction": instruction, "voice_guide": _voice(),
    }, ensure_ascii=False, indent=2)
    result = llm.call_agent("editor", _prompt("editor"), payload,
                            schema=EDITOR_SCHEMA, timeout=420)
    _track(result, agents)
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"Redaktə uğursuz: {result.error}")
    return result.data


def rewrite(run_data: dict, exclude_angle_id: int | None,
            agents: list | None = None) -> dict:
    """Eyni faktlarla, amma başqa rakursla yenidən yazır."""
    angles = run_data.get("angles", [])
    banned = [a for a in angles if a.get("id") == exclude_angle_id]
    payload = json.dumps({
        "research": run_data.get("research", {}),
        "pillar": run_data.get("chosen", {}).get("pillar"),
        "local_angle_hint": run_data.get("chosen", {}).get("local_angle_potential", ""),
        "source_link": run_data.get("chosen", {}).get("link", ""),
        "recent_theses_do_not_repeat": [],
        "voice_guide": _voice(),
        "positioning": "",
        "rewrite_instruction": (
            "Bu xəbər artıq bir dəfə yazılıb və istifadəçi bəyənmədi. "
            "Aşağıdakı rakursu TƏKRAR ETMƏ, açıq şəkildə fərqli yanaşma seç: "
            + json.dumps(banned, ensure_ascii=False)
        ),
    }, ensure_ascii=False, indent=2)
    result = llm.call_agent("rewriter", _prompt("writer"), payload,
                            schema=schemas.WRITER, timeout=600)
    _track(result, agents)
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"Yenidən yazma uğursuz: {result.error}")
    return result.data


def _track(result, agents) -> None:
    if agents is None:
        return
    agents.append({
        "name": result.name, "model": result.model, "ok": result.ok,
        "total_tokens": result.total_tokens, "cost_usd": result.cost_usd,
        "duration_ms": result.duration_ms, "error": result.error,
    })
