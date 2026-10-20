"""Маскирование секретов до журнала, оболочки и запроса в модель."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_NAME = re.compile(
    r"(SECRET|PASSWORD|TOKEN|KEY|CREDENTIAL|PRIVATE|PIN)", re.IGNORECASE
)

_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]{6,}")
_HEADER_SECRET = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie)\b\s*[:=]\s*[^\s,;]+"
)
_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|access[_-]?key|card|cvv|cvc|pan|pin|пин)"
    r"\b(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SK = re.compile(r"\bsk-[A-Za-z0-9]{8,}\b")
_QUERY_KEYS = re.compile(
    r"(?i)^(password|token|secret|key|api_key|access_token|card|cvv|cvc|pin)$"
)


def secret_names_from_env(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        if key and SECRET_NAME.search(key):
            names.append(key)
    return names


def _mask_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19:
        return "***"
    return match.group(0)


def redact_text(text: str, names: list[str] | None = None, values: list[str] | None = None) -> str:
    if not text:
        return ""
    masked = _BEARER.sub(r"\1***", text)
    masked = _HEADER_SECRET.sub(lambda m: m.group(1) + ": ***", masked)
    masked = _ASSIGN.sub(lambda m: m.group(1) + m.group(2) + "***", masked)
    masked = _SK.sub("sk-***", masked)
    masked = _CARD.sub(_mask_card, masked)
    for name in names or []:
        if not name:
            continue
        pattern = re.compile(
            rf"(?i)({re.escape(name)})(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
        )
        masked = pattern.sub(lambda m: m.group(1) + m.group(2) + "***", masked)
    for secret in values or []:
        if secret and len(secret) >= 8 and secret in masked:
            masked = masked.replace(secret, "***")
    return masked


def redact_url(url: str) -> str:
    if not url or "://" not in url:
        return redact_text(url)
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if _QUERY_KEYS.match(key) or SECRET_NAME.search(key):
            query.append((key, "***"))
        else:
            query.append((key, value))
    rebuilt = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    return redact_text(rebuilt)
