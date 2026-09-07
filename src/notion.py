"""Notion Kanban — postların redaktə və izləmə paneli.

Telegram təsdiq üçün əladır, uzun mətni redaktə etmək üçün yox. Notion
bu boşluğu doldurur: kartı açırsınız, mətni normal redaktorda düzəldirsiniz,
`notion-sync` dəyişikliyi növbəyə qaytarır.

Qayda: **mətn üçün həqiqət mənbəyi Notion-dur.** Telegram-dan edilən
düzəliş də Notion-a yazılır ki, iki yerdə fərqli mətn yaranmasın.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from . import net, queue

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"

# növbə statusu → Notion sütunu
STATUS_MAP = {
    queue.PENDING: "Təsdiq gözləyir",
    queue.EDITING: "Redaktədə",
    queue.APPROVED: "Bank",
    queue.SCHEDULED: "Cədvəldə",
    queue.PUBLISHING: "Yayımlanır",
    queue.PUBLISHED: "Yayımlanıb",
    queue.SKIPPED: "Keçildi",
}
REVERSE_STATUS = {v: k for k, v in STATUS_MAP.items()}
COLUMNS = list(STATUS_MAP.values())

DB_MARKER = "avtopost-linkedin"


class NotionError(RuntimeError):
    pass


def token() -> str:
    return os.environ.get("NOTION_TOKEN", "")


def database_id() -> str:
    return os.environ.get("NOTION_DATABASE_ID", "")


def available() -> bool:
    return bool(token() and database_id())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {token()}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }


def _call(method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    resp = net.request(method, f"{API}{path}", body=body, headers=_headers(), timeout=60)
    data = resp.json()
    if resp.status >= 300:
        message = data.get("message", "")
        if data.get("code") == "object_not_found":
            raise NotionError(
                f"{message}\n"
                "  Notion-da səhifəni açın → ··· → Connections → "
                "inteqrasiyanı əlavə edin."
            )
        raise NotionError(f"Notion {resp.status}: {message or data}")
    return data


# --- qurulum ----------------------------------------------------------

def accessible_pages(limit: int = 20) -> list[dict]:
    """İnteqrasiyanın gördüyü səhifə və bazalar."""
    data = _call("POST", "/search", {"page_size": limit})
    out = []
    for obj in data.get("results", []):
        if obj.get("object") == "database":
            title = "".join(t.get("plain_text", "") for t in obj.get("title", []))
        else:
            title = ""
            for prop in (obj.get("properties") or {}).values():
                if prop.get("type") == "title":
                    title = "".join(t.get("plain_text", "") for t in prop["title"])
                    break
        out.append({"id": obj["id"], "object": obj.get("object"), "title": title})
    return out


def create_database(parent_page_id: str) -> str:
    """Kanban bazasını lazımi sahələrlə yaradır."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": "LinkedIn postları"}}],
        "description": [{"type": "text", "text": {"content": DB_MARKER}}],
        "properties": {
            "Başlıq": {"title": {}},
            "Status": {"select": {"options": [
                {"name": name, "color": color} for name, color in zip(
                    COLUMNS,
                    ["yellow", "orange", "blue", "purple", "gray", "green", "red"],
                )
            ]}},
            "Sütun": {"select": {"options": [
                {"name": n, "color": c} for n, c in
                (("agents", "blue"), ("tooling", "green"),
                 ("business", "orange"), ("research", "purple"))
            ]}},
            "Bal": {"number": {"format": "number"}},
            "Yayım vaxtı": {"date": {}},
            "Mənbə": {"url": {}},
            "LinkedIn": {"url": {}},
            "ID": {"rich_text": {}},
        },
    }
    return _call("POST", "/databases", payload)["id"]


# --- sinxronizasiya ---------------------------------------------------

def _rich(text: str) -> list:
    """Notion mətn blokları 2000 simvol həddindədir."""
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)] or [""]
    return [{"type": "text", "text": {"content": c}} for c in chunks]


def _paragraphs(text: str) -> list:
    blocks = []
    for line in (text or "").split("\n"):
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich(line) if line else []},
        })
    return blocks


def _heading(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": _rich(text)}}


def _properties(item: queue.Item) -> dict:
    props: dict = {
        "Başlıq": {"title": _rich(item.chosen.get("title", item.id)[:180])},
        "Status": {"select": {"name": STATUS_MAP.get(item.status, "Qaralama")}},
        "ID": {"rich_text": _rich(item.id)},
        "Bal": {"number": (item.scores or {}).get("overall")},
    }
    pillar = item.chosen.get("pillar")
    if pillar:
        props["Sütun"] = {"select": {"name": pillar}}
    if item.scheduled_for:
        props["Yayım vaxtı"] = {"date": {"start": item.scheduled_for}}
    if item.chosen.get("link"):
        props["Mənbə"] = {"url": item.chosen["link"]}
    if item.linkedin_url:
        props["LinkedIn"] = {"url": item.linkedin_url}
    return props


def _body(item: queue.Item) -> list:
    blocks = [_heading("Post mətni")]
    blocks += _paragraphs(item.post)
    blocks.append(_heading("Birinci şərh"))
    blocks += _paragraphs(item.first_comment)

    if item.angles:
        blocks.append(_heading("Rakurslar"))
        for angle in item.angles:
            mark = "→ " if angle.get("id") == item.chosen_angle_id else "   "
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _rich(
                    f"{mark}[{angle.get('strength')}/10] {angle.get('type')}: "
                    f"{angle.get('headline', '')}"
                )},
            })
    facts = (item.research or {}).get("facts") or []
    if facts:
        blocks.append(_heading("Fakt yoxlaması"))
        for fact in facts[:10]:
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _rich(
                    f"[{fact.get('confidence')}] {fact.get('claim', '')[:250]}"
                )},
            })
    return blocks[:95]      # Notion bir sorğuda 100 blok qəbul edir


def find_page(item_id: str) -> str | None:
    data = _call("POST", f"/databases/{database_id()}/query", {
        "filter": {"property": "ID", "rich_text": {"equals": item_id}},
        "page_size": 1,
    })
    results = data.get("results", [])
    return results[0]["id"] if results else None


def push(item: queue.Item) -> str:
    """Növbə elementini Notion-a yazır (yeni kart və ya yeniləmə)."""
    page_id = find_page(item.id)
    if page_id:
        _call("PATCH", f"/pages/{page_id}", {"properties": _properties(item)})
        return page_id
    created = _call("POST", "/pages", {
        "parent": {"database_id": database_id()},
        "properties": _properties(item),
        "children": _body(item),
    })
    return created["id"]


def _plain(block: dict) -> str:
    kind = block.get("type")
    payload = block.get(kind) or {}
    return "".join(t.get("plain_text", "") for t in payload.get("rich_text", []))


def read_page_text(page_id: str) -> tuple[str, str]:
    """Kartdan post mətnini və birinci şərhi geri oxuyur."""
    data = _call("GET", f"/blocks/{page_id}/children?page_size=100")
    section, post_lines, comment_lines = None, [], []
    for block in data.get("results", []):
        kind = block.get("type")
        text = _plain(block)
        if kind == "heading_2":
            if text.startswith("Post"):
                section = "post"
            elif text.startswith("Birinci"):
                section = "comment"
            else:
                section = None
            continue
        if kind != "paragraph":
            continue
        if section == "post":
            post_lines.append(text)
        elif section == "comment":
            comment_lines.append(text)
    return "\n".join(post_lines).strip(), "\n".join(comment_lines).strip()


def pull() -> list[str]:
    """Notion-dakı dəyişiklikləri növbəyə qaytarır."""
    data = _call("POST", f"/databases/{database_id()}/query", {"page_size": 50})
    log: list[str] = []
    for page in data.get("results", []):
        props = page.get("properties", {})
        ident = "".join(t.get("plain_text", "")
                        for t in (props.get("ID", {}).get("rich_text") or []))
        item = queue.get(ident) if ident else None
        if not item:
            continue

        changed = []
        select = (props.get("Status", {}) or {}).get("select") or {}
        new_status = REVERSE_STATUS.get(select.get("name", ""))
        if new_status and new_status != item.status:
            # Yayım vəziyyətini Notion-dan dəyişməyə icazə vermirik —
            # LinkedIn-dəki reallıq burada həqiqət mənbəyidir.
            if item.status not in (queue.PUBLISHED, queue.PUBLISHING):
                item.status = new_status
                item.note("notion_status", new_status)
                changed.append(f"status→{new_status}")

        post, comment = read_page_text(page["id"])
        if post and post != item.post:
            item.post = post
            item.note("notion_edit", "mətn Notion-dan yeniləndi")
            changed.append("mətn")
        if comment and comment != item.first_comment:
            item.first_comment = comment
            changed.append("şərh")

        if changed:
            queue.save(item)
            log.append(f"{ident}: {', '.join(changed)}")
    return log


def sync() -> dict:
    """İki tərəfli sinxronizasiya: əvvəl Notion-dan oxu, sonra yaz."""
    pulled = pull()
    pushed = []
    for item in queue.all_items():
        if item.status == queue.SKIPPED and not item.linkedin_url:
            continue
        try:
            push(item)
            pushed.append(item.id)
        except NotionError as exc:
            pushed.append(f"{item.id}: XƏTA {exc}")
    return {"pulled": pulled, "pushed": pushed}
