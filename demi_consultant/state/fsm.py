from __future__ import annotations

from enum import StrEnum


class ChatMode(StrEnum):
    CHAT = "chat"
    CONSULTATION = "consultation"
    SKIN_TYPE = "skin_type"
    PROBLEM_SOLVING = "problem_solving"
    INGREDIENT_CHECK = "ingredient_check"
