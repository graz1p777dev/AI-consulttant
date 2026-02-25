from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Literal

EventType = Literal[
    "consultation_started",
    "skin_type_detected",
    "problem_detected",
    "recommendation_given",
    "purchase_intent",
]


@dataclass(slots=True)
class CRMEvent:
    user_id: str
    type: EventType
    payload: dict[str, Any]
    created_at: str


class CRMService(ABC):
    @abstractmethod
    def save_event(self, user_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def mark_hot_lead(self, user_id: str) -> None:
        raise NotImplementedError


class NullCRM(CRMService):
    def save_event(self, user_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        return

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        return {}

    def mark_hot_lead(self, user_id: str) -> None:
        return


class InMemoryCRM(CRMService):
    def __init__(self) -> None:
        self._events: list[CRMEvent] = []
        self._profiles: dict[str, dict[str, Any]] = {}
        self._hot_leads: set[str] = set()
        self._lock = threading.Lock()

    def save_event(self, user_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        event = CRMEvent(
            user_id=user_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._events.append(event)
            profile = self._profiles.setdefault(user_id, {"events": []})
            profile["events"].append(asdict(event))
            profile["last_event"] = event.type
            profile["updated_at"] = event.created_at

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            profile = dict(self._profiles.get(user_id, {}))
            profile["is_hot_lead"] = user_id in self._hot_leads
            return profile

    def mark_hot_lead(self, user_id: str) -> None:
        with self._lock:
            self._hot_leads.add(user_id)
            profile = self._profiles.setdefault(user_id, {"events": []})
            profile["is_hot_lead"] = True
            profile["updated_at"] = datetime.now(timezone.utc).isoformat()


class JSONFileCRM(CRMService):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self._path.exists():
            self._write_data({"events": [], "profiles": {}, "hot_leads": []})

    def save_event(self, user_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        event = CRMEvent(
            user_id=user_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            data = self._read_data()
            data["events"].append(asdict(event))
            profile = data["profiles"].setdefault(user_id, {"events": []})
            profile["events"].append(asdict(event))
            profile["last_event"] = event.type
            profile["updated_at"] = event.created_at
            self._write_data(data)

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            data = self._read_data()
            profile = dict(data["profiles"].get(user_id, {}))
            profile["is_hot_lead"] = user_id in set(data.get("hot_leads", []))
            return profile

    def mark_hot_lead(self, user_id: str) -> None:
        with self._lock:
            data = self._read_data()
            hot_leads = set(data.get("hot_leads", []))
            hot_leads.add(user_id)
            data["hot_leads"] = sorted(hot_leads)
            profile = data["profiles"].setdefault(user_id, {"events": []})
            profile["is_hot_lead"] = True
            profile["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_data(data)

    def _read_data(self) -> dict[str, Any]:
        with self._path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            raise ValueError("CRM JSON must be an object")
        data.setdefault("events", [])
        data.setdefault("profiles", {})
        data.setdefault("hot_leads", [])
        return data

    def _write_data(self, data: dict[str, Any]) -> None:
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        tmp_path.replace(self._path)


class PostgreSQLCRM(CRMService):
    """Prepared extension point for production PostgreSQL CRM backend."""

    def save_event(self, user_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        raise NotImplementedError("PostgreSQL CRM backend is not implemented yet")

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError("PostgreSQL CRM backend is not implemented yet")

    def mark_hot_lead(self, user_id: str) -> None:
        raise NotImplementedError("PostgreSQL CRM backend is not implemented yet")


def build_crm_service(*, enabled: bool, storage: str, json_path: str) -> CRMService:
    if not enabled:
        return NullCRM()

    if storage == "memory":
        return InMemoryCRM()
    if storage == "json":
        return JSONFileCRM(path=json_path)
    if storage == "postgres":
        return PostgreSQLCRM()

    raise ValueError(f"Unsupported CRM storage: {storage}")
