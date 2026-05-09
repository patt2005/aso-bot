from __future__ import annotations

import re

from core.models import Keyword


_EN_ALLOWED = re.compile(r"^[a-z0-9 \-'.&]+$")
_RO_EXTRA = "ăâîșțĂÂÎȘȚ"
_RO_ALLOWED = re.compile(rf"^[a-zA-Z0-9 \-'.&{re.escape(_RO_EXTRA)}]+$")
_HAS_LETTER = re.compile(r"[a-zA-Z]")

_NON_EN_RO_TOKENS = {
    "perekam", "suara", "panggilan", "telepon", "rekaman", "aplikasi",
    "grabador", "llamadas", "llamada", "grabadora",
    "registratore", "chiamate", "chiamata",
    "enregistreur", "appel", "appels",
    "anrufaufzeichnung", "anruf", "aufnahme",
    "gravador", "chamadas", "chamada",
    "kaydedici", "arama", "ses",
    "nagrywanie", "rozmow", "rozmowy",
    "zaznam", "hovoru",
}


def normalize(name: str) -> str:
    return " ".join(name.lower().split())


def _has_foreign_token(name: str) -> bool:
    tokens = re.split(r"[^a-zA-Z]+", name)
    return any(t and t.lower() in _NON_EN_RO_TOKENS for t in tokens)


def _passes_en(name: str) -> bool:
    if not name:
        return False
    if not _EN_ALLOWED.match(name):
        return False
    if not _HAS_LETTER.search(name):
        return False
    if _has_foreign_token(name):
        return False
    return True


def _passes_ro(name: str) -> bool:
    if not name:
        return False
    if not _RO_ALLOWED.match(name):
        return False
    if not re.search(rf"[a-zA-Z{re.escape(_RO_EXTRA)}]", name):
        return False
    if _has_foreign_token(name):
        return False
    return True


def is_acceptable_language(name: str, allowed_iso: list[str]) -> bool:
    candidate = normalize(name)
    for iso in allowed_iso:
        code = iso.upper()
        if code == "EN" and _passes_en(candidate):
            return True
        if code == "RO" and _passes_ro(candidate):
            return True
        if code not in {"EN", "RO"}:
            return True
    return False


def filter_keywords(keywords: list[Keyword], allowed_iso: list[str]) -> list[Keyword]:
    return [kw for kw in keywords if is_acceptable_language(kw.name, allowed_iso)]
