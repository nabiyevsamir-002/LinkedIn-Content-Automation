"""Telegram Bot API müştərisi.

Transport ayrıca qatdır: real HTTP və ya saxta (test) transport.
Bu, bütün təsdiq məntiqini bot tokeni olmadan sınamağa imkan verir.
"""
from __future__ import annotations

import json
import mimetypes
import pathlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import config, net, store

OFFSET_FILE = config.STATE_DIR / "telegram_offset.json"
API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


class Transport(Protocol):
    def call(self, method: str, payload: dict,
             file_field: str | None = None,
             file_path: pathlib.Path | None = None,
             http_timeout: int | None = None,
             extra_files: dict | None = None) -> dict: ...


# --- real transport ---------------------------------------------------

class HttpTransport:
    def __init__(self, token: str):
        if not token:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN boşdur. @BotFather-dən bot yaradın və "
                "tokeni .env faylına yazın."
            )
        self.token = token

    def call(self, method, payload, file_field=None, file_path=None,
             http_timeout=None, extra_files=None) -> dict:
        url = API.format(token=self.token, method=method)
        if extra_files:
            body, content_type = _multipart_many(payload, extra_files)
            raw = net.post(url, body, headers={"Content-Type": content_type}, timeout=180)
        elif file_field and file_path:
            body, content_type = _multipart(payload, file_field, pathlib.Path(file_path))
            raw = net.post(url, body, headers={"Content-Type": content_type}, timeout=120)
        else:
            raw = net.post(
                url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=http_timeout or 120,
            )
        data = json.loads(raw.decode("utf-8"))
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', data)}")
        return data.get("result", {})


def _multipart_many(fields: dict, files: dict) -> tuple[bytes, str]:
    """Bir neçə fayllı multipart — albom göndərişi üçün."""
    boundary = f"----avtopost{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        if value is None:
            continue
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    for key, path in files.items():
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; '
            f'filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8")
        )
        parts.append(path.read_bytes())
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _multipart(fields: dict, file_field: str, path: pathlib.Path) -> tuple[bytes, str]:
    boundary = f"----avtopost{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        if value is None:
            continue
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8")
    )
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


# --- test transportu --------------------------------------------------

@dataclass
class MockTransport:
    """Sınaq üçün: çağırışları yazır, hazır cavablar qaytarır."""
    calls: list = field(default_factory=list)
    updates: list = field(default_factory=list)
    _message_id: int = 1000

    def call(self, method, payload, file_field=None, file_path=None,
             http_timeout=None, extra_files=None) -> dict:
        self.calls.append({"method": method, "payload": payload,
                           "file": str(file_path) if file_path else None,
                           "files": list((extra_files or {}).values())})
        if method == "sendMediaGroup":
            self._message_id += len(extra_files or {})
            return [{"message_id": self._message_id - i}
                    for i in range(len(extra_files or {}))]
        if method in ("sendMessage", "sendPhoto"):
            self._message_id += 1
            return {"message_id": self._message_id, "chat": {"id": payload.get("chat_id")}}
        if method == "getUpdates":
            out, self.updates = self.updates, []
            return out
        if method == "getMe":
            return {"id": 1, "username": "test_bot", "first_name": "Test"}
        return {}


# --- yüksək səviyyəli API ---------------------------------------------

class Bot:
    def __init__(self, transport: Transport | None = None, chat_id: str | None = None):
        self.transport = transport or HttpTransport(config.TELEGRAM_TOKEN)
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        if not self.chat_id:
            raise TelegramError(
                "TELEGRAM_CHAT_ID boşdur. Bota bir mesaj yazın, sonra "
                "`make tg-chatid` ilə ID-ni öyrənin."
            )

    # -- göndərmə --
    def send_message(self, text: str, keyboard: list | None = None,
                     reply_to: int | None = None) -> int:
        payload: dict[str, Any] = {
            "chat_id": self.chat_id, "text": text[:4096],
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        return self.transport.call("sendMessage", payload).get("message_id", 0)

    def send_photo(self, path: str | pathlib.Path, caption: str,
                   keyboard: list | None = None) -> int:
        payload: dict[str, Any] = {
            "chat_id": self.chat_id, "caption": caption[:1024], "parse_mode": "HTML",
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        return self.transport.call(
            "sendPhoto", payload, file_field="photo", file_path=pathlib.Path(path)
        ).get("message_id", 0)

    def send_document(self, path, caption: str = "",
                      keyboard: list | None = None) -> int:
        """PDF/sənəd göndərir — karusel önizləməsi üçün."""
        payload: dict[str, Any] = {
            "chat_id": self.chat_id, "caption": caption[:1024],
            "parse_mode": "HTML",
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        return self.transport.call(
            "sendDocument", payload, file_field="document",
            file_path=pathlib.Path(path)).get("message_id", 0)

    def send_media_group(self, paths: list, caption: str = "") -> list[int]:
        """Bir neçə şəkli tək mesajda göndərir (albom).

        Telegram albomda düymə dəstəkləmir — ona görə seçim düymələri
        ayrıca mesajla gedir.
        """
        media, files = [], {}
        for index, path in enumerate(paths[:10]):
            key = f"photo{index}"
            files[key] = pathlib.Path(path)
            entry = {"type": "photo", "media": f"attach://{key}"}
            if index == 0 and caption:
                entry["caption"] = caption[:1024]
                entry["parse_mode"] = "HTML"
            media.append(entry)
        result = self.transport.call(
            "sendMediaGroup", {"chat_id": self.chat_id, "media": media},
            file_field=None, file_path=None, extra_files=files,
        )
        return [m.get("message_id", 0) for m in (result or [])]

    def edit_markup(self, message_id: int, keyboard: list | None) -> None:
        """Köhnə mesajın düymələrini silir. Alınmasa axını dayandırmır."""
        try:
            self.transport.call("editMessageReplyMarkup", {
                "chat_id": self.chat_id, "message_id": message_id,
                "reply_markup": {"inline_keyboard": keyboard or []},
            })
        except Exception:  # noqa: BLE001 — bəzək əməliyyatıdır
            pass

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        """Düymədəki «gözlə» animasiyasını söndürür.

        KRİTİK: bu çağırış UĞURSUZ OLA BİLƏR və bu normaldır.
        Telegram callback_query-ni qısa müddət saxlayır; bizim `poll`
        isə 10+ dəqiqə sonra işləyə bilər — o vaxt Telegram 400 qaytarır.
        Bu, sırf vizual təsdiqdir; xətası əsas əməliyyatı HEÇ VAXT
        dayandırmamalıdır (əvvəllər dayandırırdı və düymələr «işləmirdi»).
        """
        try:
            self.transport.call("answerCallbackQuery",
                                {"callback_query_id": callback_id,
                                 "text": text[:200]})
        except Exception:  # noqa: BLE001
            pass

    # -- qəbul --
    def get_updates(self, timeout: int = 0) -> list[dict]:
        """Yeniləmələri çəkir.

        `timeout > 0` — uzun polling: Telegram yeniləmə gələnə qədər
        bağlantını açıq saxlayır, ona görə cavab saniyələr içində gəlir.
        Bu, «düyməyə basdım, heç nə olmur» probleminin əsl həllidir.
        """
        payload = {"offset": load_offset(), "timeout": timeout,
                   "allowed_updates": ["message", "callback_query"]}
        try:
            updates = self.transport.call(
                "getUpdates", payload,
                http_timeout=timeout + 15 if timeout else None,
            ) or []
        except TelegramError as exc:
            # 409 = başqa proses eyni anda getUpdates çağırır
            # (məsələn `make watch` və cron tick). Bu, nasazlıq deyil —
            # digər dinləyici yeniləməni götürəcək.
            if "conflict" in str(exc).lower() or "409" in str(exc):
                return []
            raise
        except (TimeoutError, OSError) as exc:
            # Uzun polling-də oxuma fasiləsi NORMALDIR: Telegram
            # yeniləmə olmayanda bağlantını sadəcə bağlayır. Bunu xəta
            # saymaq lazımsız həyəcan siqnalı yaradır. Offset irəliləmir,
            # ona görə heç bir yeniləmə itmir — sadəcə yenidən soruşuruq.
            if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
                return []
            raise
        if updates:
            save_offset(max(u["update_id"] for u in updates) + 1)
        return updates

    def me(self) -> dict:
        return self.transport.call("getMe", {})


# --- offset (təkrar emalın qarşısını alır) ----------------------------

def load_offset() -> int:
    try:
        return int((store.read_json(OFFSET_FILE, {}) or {}).get("offset", 0))
    except (TypeError, ValueError):
        return 0


def save_offset(value: int) -> None:
    store.write_json(OFFSET_FILE, {"offset": value}, indent=None)


def available() -> bool:
    return bool(config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID)
