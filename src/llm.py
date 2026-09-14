"""Claude Code-u başsız (headless) agent kimi çağıran wrapper.

Əsas fikir: `claude -p` sizin Pro abunəliyinizlə işləyir, ona görə
API xərci yoxdur. Kvotanı qorumaq üçün iki mühüm optimizasiya var:

  --system-prompt  → Claude Code-un böyük default sistem promptunu tamamilə
                     əvəz edir (əlavə etmir). Çağırış başına ~8k token qənaət.
  --tools ""       → alət tərifləri göndərilmir. Web lazım olmayan agentlər
                     üçün daha ~2k token qənaət.

Hər çağırışın real token/xərc telemetriyası qaytarılır — təxmin etmirik, ölçürük.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from . import config


class NotLoggedIn(RuntimeError):
    """`claude setup-token` işlədilməyib."""


class QuotaExhausted(RuntimeError):
    """Abunəlik limiti bitib — bankdan yayımlamaq lazımdır."""


# Gözləmə real vaxtın bu qədərini yeyirsə, səbəb model deyil: kvota
# pəncərəsi, proses növbəsi və ya şəbəkə. 09.09.2026-da bir şəkil
# qaçışı 6 saat sürdü, telemetriya isə 142s göstərdi — çünki yalnız
# claude CLI-nin öz ölçüsü yazılırdı.
STALL_RATIO = 3.0
STALL_FLOOR_MS = 60_000


@dataclass
class AgentResult:
    name: str
    ok: bool
    text: str = ""
    data: Any = None
    usage: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    duration_ms: int = 0        # modelin öz ölçüsü (claude CLI verir)
    wall_ms: int = 0            # real divar saatı — gözləmə də daxil
    model: str = ""
    error: str | None = None

    @property
    def stalled(self) -> bool:
        """Real vaxt modelin ölçüsündən qat-qat böyükdürmü?"""
        if not self.wall_ms or not self.duration_ms:
            return False
        return (self.wall_ms - self.duration_ms >= STALL_FLOOR_MS
                and self.wall_ms >= self.duration_ms * STALL_RATIO)

    @property
    def total_tokens(self) -> int:
        u = self.usage or {}
        return (
            u.get("input_tokens", 0)
            + u.get("cache_read_input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0)
            + u.get("output_tokens", 0)
        )


def _login_help() -> str:
    if not config.OAUTH_TOKEN:
        return (
            ".env faylında CLAUDE_CODE_OAUTH_TOKEN boşdur.\n"
            "  1) terminalda:  claude setup-token\n"
            "  2) çıxan tokeni .env faylına yazın: CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-..."
        )
    return (
        "Token .env-də var, amma qəbul edilmədi (bitib və ya səhvdir).\n"
        "  Yenisini yaradın:  claude setup-token"
    )


_LOGIN_PAT = re.compile(r"not logged in|please run /login|invalid api key", re.I)
# Büdcə həddi işə düşəndə TƏKRAR CƏHD ETMƏK OLMAZ — hər cəhd həddi
# yenidən xərcləyir. Bir dəfə dayanırıq və nəticəni olduğu kimi qaytarırıq.
_BUDGET_PAT = re.compile(r"budget|max.?budget|spend limit", re.I)

# Claude CLI-nin limit mesajları vaxtla dəyişir. 14.09.2026: «You've hit
# your weekly limit · resets 6pm» heç bir nümunəyə uymadı → adi xəta kimi
# təkrar cəhd edildi və log-a «uyğun xəbər tapılmadı» yazıldı; istifadəçi
# limiti öz hesabından öyrəndi (dərs 11 — ehtiyat görünən olmalıdır).
_QUOTA_PAT = re.compile(
    r"usage limit|rate.?limit|quota|too many requests"
    r"|(?:weekly|daily|monthly|session) limit|hit your limit"
    r"|resets (?:at\b|\d)",
    re.I,
)


def _env(max_turns: str | None = None) -> dict:
    """Alt-proses mühiti: abunəlik tokeni açıq şəkildə ötürülür."""
    env = os.environ.copy()
    if max_turns:
        env["CLAUDE_CODE_MAX_TURNS"] = str(max_turns)
    if config.OAUTH_TOKEN:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = config.OAUTH_TOKEN
        # API açarı varsa, abunəlik əvəzinə o işlədilər — qarışmasın.
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def _build_argv(model: str, tools: str, schema: dict | None, system_prompt: str,
                budget_usd: float | None = None) -> list[str]:
    argv = [
        config.CLAUDE_BIN,
        "-p",
        "--model", model,
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--tools", tools,
        "--no-session-persistence",
        "--disable-slash-commands",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if config.SAFE_MODE:
        argv.append("--safe-mode")
    if tools:
        # Web agentləri üçün alətləri əvvəlcədən icazəli edirik ki,
        # başsız rejimdə icazə sualı axını bloklamasın.
        argv += ["--allowedTools", tools, "--permission-mode", "dontAsk"]
    else:
        argv += ["--permission-mode", "dontAsk"]
    if budget_usd:
        # Qaçaq agentə qarşı sərt hədd (abunəlikdə də xərci izləyir).
        argv += ["--max-budget-usd", f"{budget_usd:.4f}"]
    if schema:
        argv += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    return argv


def extract_json(text: str) -> Any:
    """Modelin cavabından JSON çıxarır — sərbəst mətn qarışsa belə."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def call_agent(
    name: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    tools: str = "",
    schema: dict | None = None,
    expect_json: bool = True,
    retries: int = 2,
    timeout: int = 600,
    budget_usd: float | None = None,
    max_turns: str | None = None,
) -> AgentResult:
    """Bir agenti işə salır və nəticəni telemetriya ilə qaytarır."""
    model = model or config.MODEL_MAIN
    last_error = ""
    # Son cəhddə sxemi ataraq yenidən sınayırıq: --json-schema bəzi
    # mühitlərdə dəstəklənməyə bilər, amma promptlar onsuz da JSON tələb edir.
    for attempt in range(retries + 1):
        # Sxemi yalnız SON təkrar cəhddə atırıq (ehtiyat yol).
        # Diqqət: retries=0 olanda ilk cəhd həm də sonuncudur — sxem
        # atılmamalıdır, əks halda struktur zəmanəti itir.
        drop_schema = bool(schema) and retries > 0 and attempt == retries
        argv = _build_argv(model, tools, None if drop_schema else schema,
                           system_prompt, budget_usd or config.AGENT_BUDGET_USD)
        started = time.time()
        try:
            proc = subprocess.run(
                argv,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(config.ROOT),
                env=_env(max_turns),
            )
        except subprocess.TimeoutExpired:
            last_error = f"timeout ({timeout}s)"
            continue

        raw = (proc.stdout or "").strip()
        payload = extract_json(raw) if raw else None
        blob = f"{raw}\n{proc.stderr or ''}"

        if isinstance(payload, dict) and "result" in payload:
            body = payload.get("result") or ""
            is_error = bool(payload.get("is_error"))
            usage = payload.get("usage") or {}
            cost = float(payload.get("total_cost_usd") or 0.0)
            duration = int(payload.get("duration_ms") or 0)

            if is_error:
                if _LOGIN_PAT.search(body):
                    raise NotLoggedIn(_login_help())
                if _QUOTA_PAT.search(body):
                    raise QuotaExhausted(body.strip()[:300])
                last_error = body.strip()[:300]
                if _BUDGET_PAT.search(body):
                    return AgentResult(
                        name=name, ok=False, text=body, usage=usage,
                        cost_usd=cost, duration_ms=duration, model=model,
                        wall_ms=int((time.time() - started) * 1000),
                        error=f"büdcə həddi aşıldı (təkrar cəhd edilmir): {last_error}",
                    )
                time.sleep(2 * (attempt + 1))
                continue

            data = extract_json(body) if expect_json else None
            if expect_json and data is None:
                last_error = "cavabdan JSON çıxarıla bilmədi"
                time.sleep(2 * (attempt + 1))
                continue

            return AgentResult(
                name=name, ok=True, text=body, data=data, usage=usage,
                cost_usd=cost, duration_ms=duration, model=model,
                wall_ms=int((time.time() - started) * 1000),
            )

        if _LOGIN_PAT.search(blob):
            raise NotLoggedIn(_login_help())
        if _QUOTA_PAT.search(blob):
            raise QuotaExhausted(blob.strip()[:300])

        last_error = (proc.stderr or raw or "naməlum xəta").strip()[:300]
        time.sleep(2 * (attempt + 1))

    return AgentResult(
        name=name, ok=False, model=model, error=last_error,
        duration_ms=int((time.time() - started) * 1000),
        wall_ms=int((time.time() - started) * 1000),
    )
