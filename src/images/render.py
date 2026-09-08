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


def brand_block(color: str = "") -> str:
    """İmza zolağı — hər şəkildə eyni yerdə, eyni ölçüdə.

    Dizayn agentinə buraxılsa hər dəfə fərqli yerdə və ölçüdə çıxır.
    Brend ardıcıllığı isə məhz təkrarlanmaqdan yaranır — ona görə
    bu blok proqramla, sabit şəkildə əlavə olunur.
    """
    name = config.BRAND_NAME or _linkedin_name()
    if not name:
        return ""
    accent = color or config.BRAND_COLOR or "currentColor"
    logo = logo_data_uri()
    logo_html = (
        f'<img src="{logo}" alt="" style="height:44px;width:auto;'
        f'max-width:180px;object-fit:contain;opacity:.9">' if logo else
        f'<span style="display:inline-block;width:26px;height:3px;'
        f'background:{accent};opacity:.8;border-radius:2px"></span>'
    )
    handle = (
        f'<div style="font-size:17px;opacity:.45;margin-top:2px;'
        f'letter-spacing:.2px">{config.BRAND_HANDLE}</div>'
        if config.BRAND_HANDLE else ""
    )
    return (
        f'<div style="position:absolute;left:88px;bottom:66px;z-index:50;'
        f'display:flex;align-items:center;gap:14px;'
        f'font-family:\'Inter\',sans-serif;color:inherit">'
        f'{logo_html}'
        f'<div><div style="font-size:23px;font-weight:600;opacity:.62;'
        f'letter-spacing:.2px">{name}</div>{handle}</div>'
        f'</div>'
    )


def _linkedin_name() -> str:
    try:
        from .. import linkedin

        token = linkedin.load_token()
        return token.name if token else ""
    except Exception:  # noqa: BLE001
        return ""


def wrap(body_html: str, extra_css: str = "", *, brand: bool = True) -> str:
    """Dizayn HTML-ini render üçün tam sənədə çevirir."""
    signature = brand_block() if brand else ""
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


def fit_photo(src: pathlib.Path, dst: pathlib.Path) -> pathlib.Path:
    """Stok fotonu 1200×1500 formatına kəsir (mərkəzdən)."""
    from PIL import Image

    with Image.open(src) as im:
        im = im.convert("RGB")
        target = WIDTH / HEIGHT
        w, h = im.size
        if w / h > target:                      # çox geniş → yanlardan kəs
            new_w = int(h * target)
            box = ((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h)
        else:                                   # çox hündür → yuxarı/aşağıdan kəs
            new_h = int(w / target)
            top = int((h - new_h) * 0.35)       # üst hissə adətən daha maraqlıdır
            box = (0, top, w, top + new_h)
        im.crop(box).resize((WIDTH, HEIGHT), Image.LANCZOS).save(dst, "PNG", optimize=True)
    return dst
