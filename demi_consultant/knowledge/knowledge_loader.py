from __future__ import annotations

from dataclasses import dataclass
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KnowledgeBundle:
    store_profile: dict[str, Any]
    allowed_ingredients: dict[str, Any]
    conversion_rules: dict[str, Any]


class KnowledgeLoader:
    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent
        self._base_dir = base_dir

    def load(self) -> KnowledgeBundle:
        return KnowledgeBundle(
            store_profile=self._load_json("store_profile.json"),
            allowed_ingredients=self._load_json("allowed_ingredients.json"),
            conversion_rules=self._load_json("conversion_rules.json"),
        )

    def _load_json(self, filename: str) -> dict[str, Any]:
        path = self._base_dir / filename
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            raise ValueError(f"Knowledge file must contain an object: {path}")
        return data


@lru_cache(maxsize=1)
def get_knowledge_bundle() -> KnowledgeBundle:
    return KnowledgeLoader().load()
