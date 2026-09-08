"""Karusel (sənəd) postu — sürüşdürülən slaydlar.

LinkedIn-də ən yüksək çatımı alan format budur: hər sürüşdürmə
«əlaqə» sayılır və alqoritm bunu mükafatlandırır.

Memarlıq qərarı: slaydların DİZAYNI koddadır, agentə buraxılmır.
Karuseldə slaydlar arasında vizual ardıcıllıq vacibdir — agent hər
slaydı fərqli çəkərdi. Agent yalnız MƏTNİ verir.
"""
from __future__ import annotations

import html
import json
import pathlib

from .. import config, llm
from . import render

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"}, "kicker": {"type": "string"},
                    "headline": {"type": "string"}, "value": {"type": "string"},
                    "unit": {"type": "string"}, "body": {"type": "string"},
                },
                "required": ["kind", "headline"],
            },
        },
    },
    "required": ["title", "slides"],
}

PALETTES = {
    "gecə": {"bg": "linear-gradient(155deg,#0a1020 0%,#132741 60%,#0d1b2e 100%)",
             "fg": "#f8fafc", "accent": "#38bdf8", "muted": "#8296b0"},
    "siqnal": {"bg": "#08080a", "fg": "#fafafa", "accent": "#facc15",
               "muted": "#8a8a8a"},
    "od": {"bg": "linear-gradient(150deg,#1a0b0b,#2d1410)", "fg": "#fff7ed",
           "accent": "#fb7185", "muted": "#a1887f"},
}


def _esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


def _slide_html(slide: dict, index: int, total: int, pal: dict) -> str:
    """Bir slaydın HTML-i. Şablon sabitdir — ardıcıllıq buradan gəlir."""
    kind = (slide.get("kind") or "point").lower()
    accent, fg, muted = pal["accent"], pal["fg"], pal["muted"]

    kicker = (
        f'<div style="font-size:24px;font-weight:600;letter-spacing:3px;'
        f'color:{accent};text-transform:uppercase">{_esc(slide.get("kicker"))}</div>'
        if slide.get("kicker") else ""
    )
    body = (
        f'<div style="font-size:32px;line-height:1.42;color:{muted};'
        f'margin-top:30px;max-width:940px">{_esc(slide.get("body"))}</div>'
        if slide.get("body") else ""
    )

    if kind == "number" and slide.get("value"):
        core = (
            f'<div style="display:flex;align-items:baseline;gap:18px;margin-top:22px">'
            f'<span style="font-size:200px;font-weight:800;color:{accent};'
            f'letter-spacing:-8px;line-height:.95">{_esc(slide["value"])}</span>'
            f'<span style="font-size:38px;font-weight:600;color:{muted}">'
            f'{_esc(slide.get("unit"))}</span></div>'
            f'<div style="font-size:52px;font-weight:700;line-height:1.16;'
            f'margin-top:26px;letter-spacing:-1px">{_esc(slide.get("headline"))}</div>'
        )
    elif kind == "quote":
        core = (
            f'<div style="font-size:150px;line-height:.7;color:{accent};'
            f'opacity:.28;font-weight:800">«</div>'
            f'<div style="font-size:64px;font-weight:700;line-height:1.2;'
            f'margin-top:14px;letter-spacing:-1.2px">{_esc(slide.get("headline"))}</div>'
        )
    else:
        size = 76 if kind == "cover" else 60
        core = (
            f'<div style="font-size:{size}px;font-weight:800;line-height:1.1;'
            f'margin-top:24px;letter-spacing:-2px">{_esc(slide.get("headline"))}</div>'
        )

    swipe = ""
    if kind == "cover":
        swipe = (f'<div style="position:absolute;right:88px;bottom:150px;'
                 f'font-size:30px;color:{accent};font-weight:600">sürüşdürün →</div>')

    dots = "".join(
        f'<span style="width:{28 if i == index else 10}px;height:10px;'
        f'border-radius:5px;background:{accent if i == index else muted};'
        f'opacity:{1 if i == index else .35};display:inline-block"></span>'
        for i in range(total)
    )

    return (
        f'<div style="width:1200px;height:1500px;background:{pal["bg"]};'
        f'color:{fg};padding:96px 88px;position:relative;overflow:hidden;'
        f'display:flex;flex-direction:column;justify-content:center">'
        f'<div style="position:absolute;inset:0;opacity:.04;'
        f'background:repeating-linear-gradient(0deg,{fg} 0 1px,transparent 1px 88px),'
        f'repeating-linear-gradient(90deg,{fg} 0 1px,transparent 1px 88px)"></div>'
        f'<div style="position:relative">{kicker}{core}{body}</div>'
        f'{swipe}'
        f'<div style="position:absolute;left:88px;bottom:96px;display:flex;'
        f'gap:8px;align-items:center">{dots}</div>'
        f'<div style="position:absolute;right:88px;bottom:92px;font-size:24px;'
        f'color:{muted};font-weight:600">{index + 1}/{total}</div>'
        f'</div>'
    )


def plan_slides(post: str, research: dict, agents: list | None = None) -> dict:
    """Agentdən slayd məzmununu alır (dizayn yox, yalnız mətn)."""
    payload = json.dumps({
        "post": post,
        "numbers": (research or {}).get("numbers", []),
        "facts": (research or {}).get("facts", [])[:8],
    }, ensure_ascii=False, indent=2)
    result = llm.call_agent(
        "carousel", (config.PROMPTS_DIR / "carousel.md").read_text(encoding="utf-8"),
        payload, schema=SCHEMA, timeout=420)
    if agents is not None:
        agents.append({"name": result.name, "model": result.model,
                       "ok": result.ok, "total_tokens": result.total_tokens,
                       "cost_usd": result.cost_usd,
                       "duration_ms": result.duration_ms, "error": result.error})
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(f"Karusel planı alınmadı: {result.error}")
    slides = result.data.get("slides") or []
    if len(slides) < 3:
        raise RuntimeError(f"çox az slayd ({len(slides)})")
    return result.data


def build(plan: dict, run_id: str, palette: str = "gecə") -> pathlib.Path:
    """Slaydları render edib tək PDF-ə birləşdirir."""
    from PIL import Image

    pal = PALETTES.get(palette, PALETTES["gecə"])
    slides = plan["slides"][:8]
    out_dir = config.OUT_DIR / "images" / run_id / "carousel"
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for index, slide in enumerate(slides):
        png = out_dir / f"slide-{index:02d}.png"
        # İmza yalnız SONUNCU slaydda — hər slaydda təkrarlansa yorucu olur
        html_doc = render.wrap(
            _slide_html(slide, index, len(slides), pal),
            brand=(index == len(slides) - 1), palette=palette)
        render.html_to_png(html_doc, png)
        pages.append(Image.open(png).convert("RGB"))

    pdf_path = config.OUT_DIR / "images" / run_id / "carousel.pdf"
    pages[0].save(pdf_path, "PDF", resolution=150.0, save_all=True,
                  append_images=pages[1:])
    for page in pages:
        page.close()
    return pdf_path
