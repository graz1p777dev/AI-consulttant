from __future__ import annotations

import re

_HARSH_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bу вас ужасн(ая|ый|ое) кожа\b", re.IGNORECASE), "сейчас коже нужен более бережный уход"),
    (re.compile(r"\bэто безнадежно\b", re.IGNORECASE), "это можно улучшить правильной схемой ухода"),
    (re.compile(r"\bвам срочно нужно\b", re.IGNORECASE), "рекомендую добавить"),
)


def compact_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def clean_response(text: str, fallback: str) -> str:
    if not text or not text.strip():
        return fallback

    cleaned = text.replace("\r", "").strip()
    cleaned = cleaned.replace("…", "")
    cleaned = re.sub(r"\.{3,}", "", cleaned)
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)

    for pattern, replacement in _HARSH_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # TEMP: не отрезаем хвост ответа автоматически.
    # cleaned = _drop_truncated_tail(cleaned).strip(" \n\t-,:;")
    cleaned = cleaned.strip(" \n\t-,:;")
    if not cleaned:
        return fallback

    lines = [line.rstrip() for line in cleaned.splitlines()]
    if not lines:
        return fallback

    last_line = lines[-1].strip()
    if last_line and not last_line.startswith("•") and last_line[-1] not in ".!?":
        lines[-1] = f"{last_line}."

    return "\n".join(lines).strip()


def is_simple_decline(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip(" .,!?:;")
    if not normalized:
        return False

    decline_markers = {
        "нет",
        "не надо",
        "не нужно",
        "неа",
        "нет спасибо",
        "спасибо не надо",
        "не хочу",
        "не сейчас",
    }
    return normalized in decline_markers or (normalized.startswith("нет") and len(normalized.split()) <= 3)


def _drop_truncated_tail(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""

    tail = lines[-1].strip().lower()
    if tail.endswith(("...", "-", "—", ":", ",", ";", "(")):
        lines.pop()
    elif re.search(r"\b[а-яa-z]{1,2}$", tail):
        lines.pop()

    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)
