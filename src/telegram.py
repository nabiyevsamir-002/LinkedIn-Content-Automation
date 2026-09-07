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

from . import config, net

OFFSET_FILE = config.STATE_DIR / "telegram_offset.json"
API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


class Transport(Protocol):
    def call(self, method: str, payload: dict,
             file_field: str | None = None,
             file_path: pathlib.Path | None = None) -> dict: ...


# --- real transport ---------------------------------------------------

class HttpTransport:
    def __init__(self, token: str):
        if not token:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN boşdur. @BotFather-dən bot yaradın və "
                "tokeni .env faylına yazın."
            )
        self.token = token

    def call(self, method, payload, file_field=None, file_path=None) -> dict:
        url = API.format(token=self.token, method=method)
        if file_field and file_path:
            body, content_type = _multipart(payload, file_field, pathlib.Path(file_path))
            raw = net.post(url, body, headers={"Content-Type": content_type}, timeout=120)
        else:
            raw = net.post(
                url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"}, timeout=120,
            )
        data = json.loads(raw.decode("utf-8"))
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', data)}")
        return data.get("result", {})


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

    def call(self, method, payload, file_field=None, file_path=None) -> dict:
        self.calls.append({"method": method, "payload": payload,
                           "file": str(file_path) if file_path else None})
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

    def edit_markup(self, message_id: int, keyboard: list | None) -> None:
        self.transport.call("editMessageReplyMarkup", {
            "chat_id": self.chat_id, "message_id": message_id,
            "reply_markup": {"inline_keyboard": keyboard or []},
        })

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self.transport.call("answerCallbackQuery",
                            {"callback_query_id": callback_id, "text": text[:200]})

    # -- qəbul --
    def get_updates(self, timeout: int = 0) -> list[dict]:
        payload = {"offset": load_offset(), "timeout": timeout,
                   "allowed_updates": ["message", "callback_query"]}
        updates = self.transport.call("getUpdates", payload) or []
        if updates:
            save_offset(max(u["update_id"] for u in updates) + 1)
        return updates

    def me(self) -> dict:
        return self.transport.call("getMe", {})


# --- offset (təkrar emalın qarşısını alır) ----------------------------

def load_offset() -> int:
    if not OFFSET_FILE.exists():
        return 0
    try:
        return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0))
    except (json.JSONDecodeError, OSError, ValueError):
        return 0


def save_offset(value: int) -> None:
    OFFSET_FILE.write_text(json.dumps({"offset": value}), encoding="utf-8")


def available() -> bool:
    return bool(config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID)
