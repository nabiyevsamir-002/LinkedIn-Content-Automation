"""Xəbər kartı: foto fon + başlıq zolağı.

Dizayn burada SABİTDİR — modelə buraxılmır. Model yalnız məzmun verir
(başlıq, kapsul, kateqoriya, vurğu sözləri). Səbəb `render.brand_block`
şərhində yazılanla eynidir: brend ardıcıllığı təkrarlanmaqdan yaranır,
hər dəfə yenidən dizayn edilməkdən yox.

Ölçülər 10.09.2026-da istifadəçi ilə birlikdə seçildi (bax `out/proto/`).
"""
from __future__ import annotations

import base64
import html
import json
import pathlib
import re

from .. import config

LOGO_PATH = config.ROOT / "assets" / "logo.svg"

PHOTO_H = 860          # foto sahəsi
BUBBLE_PX = 290        # dairəvi ikinci şəkil
BUBBLE_TOP = 140
BUBBLE_RIGHT = 44
ACCENT = "#38bdf8"


def _logo_svg() -> str:
    """Loqonu INLINE qaytarır — `currentColor` yalnız belə işləyir.

    `<img>` daxilindəki SVG ana sənədin rəngini görmür, ona görə
    base64 data URI burada yaramır.
    """
    if not LOGO_PATH.exists():
        return '<span class="anchor"></span>'
    svg = LOGO_PATH.read_text(encoding="utf-8")
    svg = re.sub(r"<\?xml.*?\?>", "", svg, flags=re.S).strip()
    return svg.replace("<svg ", '<svg class="logo" ', 1)


def _data_uri(path: str | pathlib.Path) -> str:
    raw = pathlib.Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode()


CAPSULE_MAX = 58        # bir sətirə sığan hədd (30px şrift, 1000px en)


def _fit_capsule(text: str) -> str:
    """Kapsul BİR sətir olmalıdır — uzun mətn yumru formanı pozur.

    Prompt hədd qoyur, amma model həmişə əməl etmir: 10.09.2026-da
    70 simvolluq kapsul iki sətirə düşdü və kart düzbucaqlıya çevrildi.
    Ona görə hədd kodda da var.
    """
    text = " ".join((text or "").split())
    if len(text) <= CAPSULE_MAX:
        return text
    cut = text[:CAPSULE_MAX].rsplit(" ", 1)[0].rstrip(" ,.;:-—")
    return (cut or text[:CAPSULE_MAX].rstrip()) + "…"


def _accent_list(value) -> list:
    """`accent_words` massiv olmalıdır, amma model bəzən JSON SƏTRİ qaytarır.

    10.09.2026: sxemdə `array` yazılmasına baxmayaraq model
    `'["Astra", "ekranı"]'` qaytardı. Python sətri HƏRF-HƏRF iterasiya
    edir, ona görə hər hərf ayrıca <em> ilə sarındı:
    `Op<em>e</em><em>n</em><em>A</em>I…` — başlıq alabəzək çıxdı.
    """
    if isinstance(value, list):
        return [str(w).strip() for w in value if str(w).strip()]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                return [str(w).strip() for w in parsed if str(w).strip()]
        return [text] if text else []
    return []


def _mark_accents(headline: str, words: list) -> str:
    """Vurğu sözlərini <em> ilə işarələyir — qalanı escape olunur.

    Uyğunluq SÖZ SƏRHƏDİ ilə axtarılır: «Astra» sözü «OpenAI»-ın içindəki
    hərflərə düşməməlidir.
    """
    safe = html.escape(headline)
    for word in sorted(_accent_list(words), key=len, reverse=True):
        target = html.escape(word)
        if not target or f"<em>{target}</em>" in safe:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(target)}(?!\w)")
        safe, count = pattern.subn(f"<em>{target}</em>", safe, count=1)
        if not count and target in safe:          # sərhəd tapılmadı — hərfi ax
            safe = safe.replace(target, f"<em>{target}</em>", 1)
    return safe


def build(director: dict, photo: str, bubble: str = "",
          brand_info: dict | None = None) -> tuple[str, str]:
    """(body_html, css) qaytarır — `render.wrap(..., brand=False)` üçün.

    `brand_info` — `images.brand()` nəticəsi. Onu KƏNARDAN alırıq, çünki
    `BRAND_NAME` CI-da təyin edilməyib və o funksiya adı LinkedIn
    tokenindən götürən ehtiyat yola malikdir. Birbaşa `config.BRAND_NAME`
    oxusaq, CI-da hazırlanan kart adsız çıxar.
    """
    headline = (director.get("headline") or "").strip()
    kicker = (director.get("kicker") or "").strip().upper()
    capsule = _fit_capsule(director.get("support") or "")
    accents = director.get("accent_words") or []

    info = brand_info or {}
    name = info.get("name") or config.BRAND_NAME or ""
    handle = (info.get("handle") or config.BRAND_HANDLE or "").strip()
    for prefix in ("https://", "http://", "www."):
        if handle.startswith(prefix):
            handle = handle[len(prefix):]
    handle = handle.rstrip("/")

    bubble_html = (
        f'<img class="bubble" src="{_data_uri(bubble)}" alt="">' if bubble else ""
    )
    kicker_html = f'<div class="kicker">{html.escape(kicker)}</div>' if kicker else ""
    capsule_html = (
        f'<div class="capsule">{html.escape(capsule)}</div>' if capsule else ""
    )
    site_html = (
        f'<div class="site">&#8853; {html.escape(handle)}</div>' if handle else ""
    )

    body = f'''<div class="card">
  <div class="photo">
    <img class="bg" src="{_data_uri(photo)}" alt="">
    <div class="shade"></div>
    <div class="topbar">{_logo_svg()}
      <span class="brand">{html.escape(name)}</span><span class="rule"></span></div>
    {kicker_html}{bubble_html}{capsule_html}
  </div>
  <div class="block"><h1>{_mark_accents(headline, accents)}</h1>{site_html}</div>
</div>'''

    css = f'''
.card{{width:1200px;height:1500px;background:#000;display:flex;
  flex-direction:column;overflow:hidden}}
.photo{{position:relative;height:{PHOTO_H}px;overflow:hidden}}
.bg{{width:100%;height:100%;object-fit:cover;object-position:center 18%;
  display:block}}
.shade{{position:absolute;inset:0;background:linear-gradient(180deg,
  rgba(0,0,0,.78) 0%,rgba(0,0,0,.15) 24%,rgba(0,0,0,0) 52%,
  rgba(0,0,0,.62) 100%)}}
.topbar{{position:absolute;top:50px;left:56px;right:0;display:flex;
  align-items:center;gap:16px;z-index:5;color:#fff}}
.logo{{width:46px;height:46px;flex:none}}
.anchor{{width:6px;height:40px;border-radius:3px;background:#fff;flex:none}}
.brand{{font-size:34px;font-weight:800;color:#fff;letter-spacing:-.4px;
  white-space:nowrap}}
.rule{{flex:1;height:3px;background:#fff;opacity:.9}}
.kicker{{position:absolute;top:126px;left:62px;font-size:23px;font-weight:800;
  letter-spacing:12px;text-transform:uppercase;color:rgba(255,255,255,.92);
  text-shadow:0 2px 12px rgba(0,0,0,.85);z-index:5}}
.bubble{{position:absolute;right:{BUBBLE_RIGHT}px;top:{BUBBLE_TOP}px;
  width:{BUBBLE_PX}px;height:{BUBBLE_PX}px;border-radius:50%;object-fit:cover;
  border:5px solid #fff;z-index:4;box-shadow:0 16px 44px rgba(0,0,0,.5)}}
.capsule{{position:absolute;left:56px;bottom:32px;background:#0a0a0a;color:#fff;
  font-size:30px;font-weight:600;padding:20px 34px;border-radius:999px;
  border:2px solid rgba(255,255,255,.22);max-width:1040px;z-index:5;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.block{{flex:1;background:#000;padding:54px 60px 0;position:relative}}
h1{{font-size:80px;line-height:1.07;font-weight:800;color:#fff;
  letter-spacing:-2.4px}}
h1 em{{font-style:normal;color:{ACCENT}}}
.site{{position:absolute;left:60px;bottom:54px;font-size:26px;
  color:rgba(255,255,255,.42)}}
'''
    return body, css
