"""Белый список действий на киоске. Оплата, логин и запуск игр требуют флага."""

from __future__ import annotations

import re

_PAYMENT = re.compile(
    r"(?i)(yookassa|yoomoney|ёкасса|оплат|пополн|checkout|pay\s*now|\bpay\b|"
    r"card[\s_-]?number|\bcvv\b|\bcvc\b|данн\w*\s+карт|чек)"
)
_LAUNCH = re.compile(
    r"(?i)(запустить игру|играть|launch|steam|epic|riot|battlenet|ubisoft|"
    r"roblox|vkplay|lesta|\bea\b|faceit)"
)
_LOGIN = re.compile(
    r"(?i)(\blogin\b|log[\s_-]?in|sign[\s_-]?in|\bвойти\b|\bвход\b|"
    r"телефон|phone|\bpin\b|\bпин\b|пароль|password)"
)
_POWER = re.compile(
    r"(?i)(выключ|перезагруз|завершить работу|shutdown|power\s*off|"
    r"log\s*off|logout|выход из сессии|выключить пк)"
)
_OS_KEY = re.compile(r"(?i)^(lwin|rwin|win|meta|super|alt\+f4|alt\+tab)$")
_PHONE = re.compile(r"\d{10,}")


def _blob(action: dict) -> str:
    parts = [
        str(action.get("selector") or ""),
        str(action.get("role") or ""),
        str(action.get("name") or ""),
        str(action.get("text") or ""),
        str(action.get("key") or ""),
    ]
    return " ".join(parts)


def rejection_reason(action: dict, policy: dict) -> str | None:
    """Вернуть причину запрета или None, если шаг можно исполнять."""
    kind = str(action.get("action") or "")
    if kind in {"done", "blocked", "wait", "scroll"}:
        return None

    blob = _blob(action)
    if _POWER.search(blob):
        return "выключение и завершение сессии запрещены"
    if kind == "press" and _OS_KEY.search(str(action.get("key") or "").strip()):
        return "системные клавиши запрещены"

    if _PAYMENT.search(blob) and not policy.get("allowPayments"):
        return "оплата запрещена политикой (allowPayments)"

    if _LAUNCH.search(blob) and not policy.get("allowLaunch"):
        return "запуск игр запрещён политикой (allowLaunch)"

    login = bool(_LOGIN.search(blob))
    if kind == "type" and _PHONE.search(str(action.get("text") or "")):
        login = True
    if login and not policy.get("allowLogin"):
        return "логин запрещён политикой (allowLogin)"
    return None
