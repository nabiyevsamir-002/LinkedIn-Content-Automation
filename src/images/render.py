"""HTML → PNG render (headless Chrome).

Niyə Chrome: SVG kitabxanalarından fərqli olaraq tam CSS, flexbox və
web-font dəstəyi var — Claude-un yazdığı dizayn olduğu kimi çıxır.
Şriftlər base64 kimi HTML-ə hopdurulur, ona görə nəticə macOS-da və
GitHub Actions-da eyni görünür (yol/şrift asılılığı yoxdur).
"""
from __future__ import annotations

import base64
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from .. import config

# LinkedIn feed-də ən çox şaquli yer tutan nisbət: 4:5
WIDTH, HEIGHT = 1200, 1500
SCALE = 2  # 2x render → Pillow ilə kiçildilir: mətn daha kəskin çıxır

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
)

FONTS_DIR = config.ROOT / "assets" / "fonts"


class RenderError(RuntimeError):
    pass


def find_chrome() -> str:
    override = os.environ.get("CHROME_BIN")
    if override and (pathlib.Path(override).exists() or shutil.which(override)):
        return override
    for candidate in CHROME_CANDIDATES:
        if pathlib.Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    raise RenderError(
        "Chrome/Chromium tapılmadı. macOS-da Google Chrome quraşdırın "
        "və ya CHROME_BIN mühit dəyişənini təyin edin."
    )


def font_css() -> str:
    """Inter şriftini base64 kimi hopdurur — Azərbaycan hərfləri zəmanətli."""
    blocks = []
    for weight in (400, 600, 800):
        path = FONTS_DIR / f"Inter-{weight}.woff2"
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode()
        blocks.append(
            "@font-face{font-family:'Inter';font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "".join(blocks)


def logo_data_uri() -> str:
    """Loqonu base64 data URI kimi qaytarır (xarici resurs qadağandır)."""
    if not config.BRAND_LOGO:
        return ""
    path = pathlib.Path(config.BRAND_LOGO)
    if not path.is_absolute():
        path = config.ROOT / path
    if not path.exists():
        return ""
    mime = {"svg": "image/svg+xml", "png": "image/png",
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp"}.get(path.suffix.lower().lstrip("."), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


# Palitra → imzanın mətn rəngi. `color:inherit` işlətmək olmaz:
# imza dizayn blokunun qardaşıdır və `body`-nin defolt qara rəngini
# miras alır — qaranlıq fonda görünmür.
_LIGHT_PALETTES = {"kağız", "kagiz", "paper", "light"}


def signature_color(palette: str = "") -> str:
    return "#14110e" if (palette or "").strip().lower() in _LIGHT_PALETTES else "#f8fafc"


LOGO_SVG_PATH = config.ROOT / "assets" / "logo.svg"


def logo_svg(size_px: int = 52, css_class: str = "brandlogo") -> str:
    """Loqonu INLINE qaytarır — `currentColor` yalnız belə işləyir.

    `<img>` + base64 data URI ilə SVG ana sənədin rəngini GÖRMÜR, yəni
    loqo açıq və tünd fonda eyni rəngdə qalır. Ona görə fayl birbaşa
    sənədə hopdurulur.
    """
    if not LOGO_SVG_PATH.exists():
        return ""
    svg = re.sub(r"<\?xml.*?\?>", "",
                 LOGO_SVG_PATH.read_text(encoding="utf-8"), flags=re.S).strip()
    return svg.replace(
        "<svg ",
        f'<svg class="{css_class}" width="{size_px}" height="{size_px}" ', 1)


def brand_block(color: str = "", palette: str = "") -> str:
    """İmza zolağı — hər şəkildə eyni yerdə, eyni ölçüdə.

    Dizayn agentinə buraxılsa hər dəfə fərqli yerdə və ölçüdə çıxır.
    Brend ardıcıllığı isə məhz təkrarlanmaqdan yaranır — ona görə
    bu blok proqramla, sabit şəkildə əlavə olunur.
    """
    name = config.BRAND_NAME or _linkedin_name()
    if not name:
        return ""
    accent = color or config.BRAND_COLOR or "currentColor"
    # Sıra: inline SN loqosu → istifadəçinin təyin etdiyi fayl → zolaq
    # BRAND_COLOR təyin olunubsa loqo da onu götürməlidir — loqo
    # `currentColor` işlədir, ona görə rəngi konteyner verir.
    inline = logo_svg(52)
    if inline and color or (inline and config.BRAND_COLOR):
        inline = f'<span style="color:{accent};display:inline-flex">{inline}</span>' 
    external = logo_data_uri() if not inline else ""
    logo_html = (
        inline or
        (f'<img src="{external}" alt="" style="height:52px;width:auto;'
         f'max-width:190px;object-fit:contain;opacity:.95">' if external else
         # Loqo yoxdursa vurğu rəngində şaquli zolaq — ad üçün lövbər
         f'<span style="display:inline-block;width:5px;height:52px;'
         f'background:{accent};border-radius:3px;opacity:.9"></span>')
    )
    handle = ""
    if config.BRAND_HANDLE:
        # Tam URL uzun olur və imzanı sıxışdırır — protokol və artıq
        # hissələri atırıq: «linkedin.com/in/samir-nabiyev»
        short = config.BRAND_HANDLE.strip()
        for prefix in ("https://", "http://", "www."):
            if short.startswith(prefix):
                short = short[len(prefix):]
        short = short.rstrip("/")
        if len(short) > 42:
            short = short[:41] + "…"
        handle = (
            f'<div style="font-size:17px;opacity:.45;margin-top:4px;'
            f'letter-spacing:.1px;white-space:nowrap;font-weight:500">'
            f'{short}</div>'
        )
    return (
        f'<div style="position:absolute;left:88px;bottom:64px;z-index:50;'
        f'display:flex;align-items:center;gap:18px;'
        f'font-family:\'Inter\',sans-serif;color:{signature_color(palette)}">'
        f'{logo_html}'
        f'<div>'
        # Ad: iri, qalın, demək olar tam qeyri-şəffaf — imzanın əsas hissəsi
        f'<div style="font-size:32px;font-weight:700;opacity:.94;'
        f'letter-spacing:-.3px;line-height:1.12">{name}</div>'
        f'{handle}'
        f'</div>'
        f'</div>'
    )


def _linkedin_name() -> str:
    try:
        from .. import linkedin

        token = linkedin.load_token()
        return token.name if token else ""
    except Exception:  # noqa: BLE001
        return ""


def wrap(body_html: str, extra_css: str = "", *, brand: bool = True,
         palette: str = "") -> str:
    """Dizayn HTML-ini render üçün tam sənədə çevirir.

    `palette` — dizaynerin seçdiyi palitra adı. İmzanın rəngi ona görə
    təyin edilir (açıq fonda qara, qaranlıqda ağ).
    """
    signature = brand_block(palette=palette) if brand else ""
    return f"""<!doctype html><html lang="az"><head><meta charset="utf-8">
<style>
{font_css()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden}}
body{{font-family:'Inter',-apple-system,'Helvetica Neue',Arial,sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  position:relative}}
{extra_css}
</style></head><body>{body_html}{signature}</body></html>"""


def html_to_png(html: str, out_path: pathlib.Path, *, timeout: int = 90) -> pathlib.Path:
    chrome = find_chrome()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # DİQQƏT: macOS-da `/var/folders/...` (default temp) Chrome üçün
    # əlçatmazdır — proses səssizcə donur. Ona görə render faylları
    # layihə daxilində, hər iki tərəfin oxuya bildiyi yerdə yaradılır.
    work_root = config.OUT_DIR / ".render"
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(work_root)) as tmp:
        page = pathlib.Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        raw = pathlib.Path(tmp) / "raw.png"
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--disable-dev-shm-usage",
            "--allow-file-access-from-files",
            "--default-background-color=00000000",
            f"--force-device-scale-factor={SCALE}",
            f"--window-size={WIDTH},{HEIGHT}",
            f"--screenshot={raw}", f"--user-data-dir={tmp}/profile",
            f"file://{page}",
        ]
        _run_chrome(cmd, raw, timeout)
        _downscale(raw, out_path)
    return out_path


def _run_chrome(cmd: list[str], target: pathlib.Path, timeout: int) -> None:
    """Chrome-u işə salır və şəkil hazır olan kimi dayandırır.

    macOS-da headless Chrome şəkli yazandan sonra çıxmır — CVDisplayLink
    run loop-u prosesi canlı saxlayır. Prosesin bitməsini gözləsək, sonsuz
    donma alınır. Ona görə faylın yaranmasını izləyirik: ölçü sabitləşən
    kimi şəkil tamdır və prosesi bağlayırıq.
    """
    import time

    log = target.parent / "chrome.log"
    with open(log, "w") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=fh)
        try:
            deadline = time.time() + timeout
            stable_size, stable_since = -1, 0.0
            while time.time() < deadline:
                if proc.poll() is not None:
                    break                      # özü çıxdı (Linux/CI davranışı)
                if target.exists():
                    size = target.stat().st_size
                    now = time.time()
                    if size > 0 and size == stable_size:
                        if now - stable_since >= 0.4:
                            break              # fayl tam yazılıb
                    else:
                        stable_size, stable_since = size, now
                time.sleep(0.15)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    if not target.exists() or target.stat().st_size == 0:
        tail = log.read_text(errors="replace")[-400:] if log.exists() else ""
        raise RenderError(f"Chrome şəkil yarada bilmədi: {tail}")


def _downscale(src: pathlib.Path, dst: pathlib.Path) -> None:
    """2x render → dəqiq 1200×1500. Pillow yoxdursa xam şəkil saxlanılır."""
    try:
        from PIL import Image

        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.size != (WIDTH, HEIGHT):
                im = im.resize((WIDTH, HEIGHT), Image.LANCZOS)
            im.save(dst, "PNG", optimize=True)
    except ImportError:
        shutil.copy(src, dst)


def crop_box(w: int, h: int, target: float, focus: list | None = None) -> tuple:
    """Kəsim pəncərəsi — fokus verilibsə subyektin ətrafında.

    `focus` = [x0, y0, x1, y1], 0-1 nisbi (müfəttişin gördüyü subyekt).
    15.09.2026: «Jensen Huang — Nvidia Keynote» fotosunda Huang kadrın
    sol-alt küncündə idi; mərkəzdən kəsim onu tamamilə atırdı. Pəncərə
    subyektin mərkəzinə çəkilir və sərhədlərə sıxılır.
    """
    if w / h > target:
        new_w, new_h = int(h * target), h
    else:
        new_w, new_h = w, int(w / target)
    if focus:
        cx = (focus[0] + focus[2]) / 2 * w
        cy = (focus[1] + focus[3]) / 2 * h
    else:
        cx = w / 2
        cy = h * 0.35 + new_h / 2 if new_h < h else h / 2   # üst hissə adətən maraqlıdır
    left = int(min(max(0, cx - new_w / 2), w - new_w))
    top = int(min(max(0, cy - new_h / 2), h - new_h))
    return (left, top, left + new_w, top + new_h)


def fit_photo(src: pathlib.Path, dst: pathlib.Path,
              focus: list | None = None, size: tuple | None = None) -> pathlib.Path:
    """Fotonu `size`-a (default 1200×1500) kəsir — fokus varsa onun ətrafında."""
    from PIL import Image

    width, height = size or (WIDTH, HEIGHT)
    with Image.open(src) as im:
        im = im.convert("RGB")
        box = crop_box(im.size[0], im.size[1], width / height, focus)
        im.crop(box).resize((width, height), Image.LANCZOS).save(dst, "PNG", optimize=True)
    return dst
