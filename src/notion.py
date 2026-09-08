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
from datetime import datetime, timedelta, timezone

from . import net, queue

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"

# Baza istifadəçinin öz sxemi ola bilər (ingilis adları, `status` tipi).
# Ona görə sabit ad əvəzinə açar sözlə uyğunlaşdırırıq.
COLUMNS = ["Təsdiq gözləyir", "Redaktədə", "Bank", "Cədvəldə",
           "Yayımlanır", "Yayımlanıb", "Keçildi"]

# Hər növbə statusu üçün Notion seçimində axtarılacaq açar sözlər
# (prioritet sırası ilə).
_STATUS_HINTS = {
    queue.PENDING: ["təsdiq", "gözlə", "not started", "todo", "yeni", "review"],
    # «Redaktədə» seçimi yoxdursa, gözləyən statusa düşməlidir —
    # bankda deyil, çünki post hələ təsdiqlənməyib.
    queue.EDITING: ["redaktə", "editing", "draft", "not started", "todo", "yeni"],
    queue.APPROVED: ["bank", "approved", "ready", "in progress"],
    # «In progress»-ə sürüşdürmək = təsdiqləmək (banka atmaq) mənasını verir
    queue.SCHEDULED: ["cədvəl", "scheduled", "planned", "in progress"],
    queue.PUBLISHING: ["yayımlanır"],   # daxili vəziyyət — Notion-dan təyin edilmir
    queue.PUBLISHED: ["yayımlanıb", "published", "done", "posted", "complete"],
    queue.SKIPPED: ["keçildi", "skip", "cancel", "archive", "done"],
}

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


# --- sxem kəşfi -------------------------------------------------------

_SCHEMA: dict | None = None


def schema(refresh: bool = False) -> dict:
    """Bazanın sahələrini oxuyur (bir dəfə, sonra keşdən)."""
    global _SCHEMA
    if _SCHEMA is None or refresh:
        _SCHEMA = _call("GET", f"/databases/{database_id()}").get("properties", {})
    return _SCHEMA


def _find(kind: str, *names: str) -> str | None:
    """Verilmiş tipdə sahəni adına görə tapır (ad siyahısı prioritetlidir)."""
    props = schema()
    lowered = {k.lower(): k for k in props}
    for name in names:
        key = lowered.get(name.lower())
        if key and props[key]["type"] == kind:
            return key
    for key, prop in props.items():
        if prop["type"] == kind:
            return key
    return None


def field_map() -> dict:
    """Növbə sahələrini bazadakı real sütun adlarına bağlayır."""
    props = schema()
    lowered = {k.lower(): k for k in props}

    def by_name(kind: str, *names: str) -> str | None:
        for name in names:
            key = lowered.get(name.lower())
            if key and props[key]["type"] == kind:
                return key
        return None

    status_key = None
    for key, prop in props.items():
        if prop["type"] in ("status", "select") and "status" in key.lower():
            status_key = key
            break
    status_key = status_key or _find("status") or _find("select")

    return {
        "title": _find("title"),
        "status": status_key,
        "content": by_name("rich_text", "Content", "Mətn", "Post"),
        "ident": by_name("rich_text", "ID", "Item ID"),
        "source": by_name("url", "Mənbə", "Source"),
        "linkedin": by_name("url", "LinkedIn", "Post URL", "URL"),
        "date": by_name("date", "Yayım vaxtı", "Publish Date", "Date"),
        "posted": by_name("checkbox", "Posted", "Yayımlandı"),
        "score": by_name("number", "Bal", "Score"),
    }


def status_options() -> list[str]:
    props = schema()
    fields = field_map()
    key = fields.get("status")
    if not key:
        return []
    prop = props[key]
    return [o["name"] for o in prop[prop["type"]].get("options", [])]


def notion_status(item_status: str) -> str | None:
    """Növbə statusuna ən yaxın Notion seçimini tapır."""
    options = status_options()
    if not options:
        return None
    for hint in _STATUS_HINTS.get(item_status, []):
        for option in options:
            if hint in option.lower():
                return option
    # Uyğun seçim yoxdursa, birinci seçimə düşmək təhlükəlidir
    # (məs. «Bank» ola bilər). Gözləyən statusa qayıdırıq.
    for hint in _STATUS_HINTS[queue.PENDING]:
        for option in options:
            if hint in option.lower():
                return option
    return options[0]


# Notion-dan gələ bilməyən vəziyyətlər: `publishing` yayım ortasındakı
# daxili keçiddir, onu kənardan təyin etmək yayımı bloklayır.
_NOT_FROM_NOTION = (queue.PUBLISHING,)


def queue_status(option_name: str) -> str | None:
    """Notion seçimindən növbə statusuna geri uyğunlaşdırma."""
    low = (option_name or "").lower()
    best, best_rank = None, 99
    for status, hints in _STATUS_HINTS.items():
        if status in _NOT_FROM_NOTION:
            continue
        for rank, hint in enumerate(hints):
            if hint in low and rank < best_rank:
                best, best_rank = status, rank
    return best


def ensure_properties() -> list[str]:
    """Əlaqə üçün mütləq lazım olan sahələri əlavə edir (mövcudlara toxunmur)."""
    fields = field_map()
    additions = {}
    if not fields["ident"]:
        additions["ID"] = {"rich_text": {}}
    if not fields["source"]:
        additions["Mənbə"] = {"url": {}}
    if not additions:
        return []
    _call("PATCH", f"/databases/{database_id()}", {"properties": additions})
    schema(refresh=True)
    return list(additions)


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
    fields = field_map()
    all_props = schema()
    props: dict = {}

    if fields["title"]:
        props[fields["title"]] = {"title": _rich(
            item.chosen.get("title", item.id)[:180])}
    if fields["ident"]:
        props[fields["ident"]] = {"rich_text": _rich(item.id)}
    if fields["status"]:
        option = notion_status(item.status)
        if option:
            kind = all_props[fields["status"]]["type"]   # status | select
            props[fields["status"]] = {kind: {"name": option}}
    if fields["content"]:
        # rich_text sahəsi 2000 simvol həddindədir — post ora sığır və
        # cədvəl görünüşündə birbaşa redaktə oluna bilir.
        props[fields["content"]] = {"rich_text": _rich(item.post[:1900])}
    if fields["score"] and (item.scores or {}).get("overall") is not None:
        props[fields["score"]] = {"number": item.scores["overall"]}
    if fields["date"] and item.scheduled_for:
        props[fields["date"]] = {"date": {"start": item.scheduled_for}}
    if fields["source"] and item.chosen.get("link"):
        props[fields["source"]] = {"url": item.chosen["link"]}
    if fields["linkedin"] and item.linkedin_url:
        props[fields["linkedin"]] = {"url": item.linkedin_url}
    if fields["posted"]:
        props[fields["posted"]] = {"checkbox": item.status == queue.PUBLISHED}
    return props


def _body(item: queue.Item) -> list:
    blocks = []
    if not field_map()["content"]:      # Content sahəsi yoxdursa mətn gövdədə
        blocks.append(_heading("Post mətni"))
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
    ident = field_map()["ident"]
    if not ident:
        return None
    data = _call("POST", f"/databases/{database_id()}/query", {
        "filter": {"property": ident, "rich_text": {"equals": item_id}},
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


def _newer_than_queue(page: dict, item: queue.Item) -> bool:
    """Notion kartı növbədəki elementdən sonra dəyişdirilibmi?

    Bu yoxlama olmasa KÖHNƏ Notion kartı YENİ növbə statusunu üstələyir:
    məsələn Telegram-dan təsdiqlədiyiniz post, hələ yenilənməmiş
    Notion kartına görə «pending»-ə qayıdır. Bu, real baş verdi.
    """
    edited = page.get("last_edited_time")
    if not edited or not item.updated_at:
        return True
    try:
        notion_at = datetime.fromisoformat(edited.replace("Z", "+00:00"))
        queue_at = datetime.fromisoformat(item.updated_at)
    except ValueError:
        return True
    if queue_at.tzinfo is None:
        queue_at = queue_at.replace(tzinfo=timezone.utc)
    # Notion saniyə dəqiqliyi ilə saxlayır — kiçik fərqlərə güzəşt
    return notion_at >= queue_at - timedelta(seconds=2)


def pull() -> list[str]:
    """Notion-dakı dəyişiklikləri növbəyə qaytarır.

    Yalnız Notion kartı növbədəki elementdən YENİ olduqda tətbiq edilir.
    """
    data = _call("POST", f"/databases/{database_id()}/query", {"page_size": 50})
    log: list[str] = []
    fields = field_map()
    for page in data.get("results", []):
        props = page.get("properties", {})
        ident = ""
        if fields["ident"]:
            ident = "".join(t.get("plain_text", "") for t in
                            ((props.get(fields["ident"]) or {}).get("rich_text") or []))
        item = queue.get(ident) if ident else None
        if not item:
            continue
        if not _newer_than_queue(page, item):
            continue          # növbə daha yenidir — Notion-u üstələmirik

        changed = []
        status_prop = props.get(fields["status"]) or {} if fields["status"] else {}
        chosen = (status_prop.get("status") or status_prop.get("select") or {})
        new_status = queue_status(chosen.get("name", ""))
        if new_status and new_status != item.status:
            # Yayım vəziyyətində həqiqət mənbəyi LinkedIn-dir, Notion yox.
            if item.status in (queue.PUBLISHED, queue.PUBLISHING):
                pass
            elif new_status == queue.PUBLISHED and not item.linkedin_urn:
                # «Done»-a sürüşdürülüb, amma LinkedIn-ə heç nə getməyib.
                # Bunu qəbul etsək post sakitcə itər — rədd edib qeyd edirik.
                item.note("notion_status_rejected",
                          "«yayımlanıb» qəbul edilmədi: LinkedIn URN yoxdur")
                queue.save(item)
                log.append(f"{ident}: ⚠ «Done» rədd edildi — post hələ "
                           f"yayımlanmayıb (keçmək üçün «Keçildi» seçimi əlavə edin)")
            else:
                item.status = new_status
                item.note("notion_status", new_status)
                changed.append(f"status→{new_status}")

        post, comment = read_page_text(page["id"])
        if fields["content"]:
            content = "".join(
                t.get("plain_text", "") for t in
                ((props.get(fields["content"]) or {}).get("rich_text") or [])
            ).strip()
            if content:
                post = content
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
    added = ensure_properties()
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
    return {"pulled": pulled, "pushed": pushed, "added_fields": added}
