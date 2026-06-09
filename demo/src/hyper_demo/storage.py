from __future__ import annotations

import json
import threading
from json import JSONDecodeError
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from hyper_demo.config import Settings, get_settings, runtime_from_settings
from hyper_demo.models import (
    AgentTradeAnalysis,
    ConnectedWallet,
    DemoRun,
    InvestorProfile,
    OrderRecord,
    PrivyAgentWallet,
    ResearchReport,
    RunEvent,
    RuntimeSettings,
    TradePlan,
)

T = TypeVar("T", bound=BaseModel)
_STORE_LOCK = threading.Lock()


class JsonStore:
    """Tiny JSON document store for local demo state."""

    collections = {
        "profiles": InvestorProfile,
        "analysis": AgentTradeAnalysis,
        "research": ResearchReport,
        "plans": TradePlan,
        "orders": OrderRecord,
        "runs": DemoRun,
        "events": RunEvent,
        "runtime": RuntimeSettings,
        "connected_wallet": ConnectedWallet,
        "privy_agent_wallet": PrivyAgentWallet,
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.demo_state_dir)
        if not self.root.is_absolute():
            self.root = Path.cwd() / self.root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, collection: str) -> Path:
        if collection not in self.collections:
            raise KeyError(f"Unknown collection: {collection}")
        return self.root / f"{collection}.json"

    def _read_raw(self, collection: str) -> list[dict[str, Any]]:
        path = self._path(collection)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _write_raw(self, collection: str, records: list[dict[str, Any]]) -> None:
        path = self._path(collection)
        payload = json.dumps(records, indent=2, default=str)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(path)

    def list(self, collection: str) -> list[T]:
        model = self.collections[collection]
        items: list[T] = []
        for record in self._read_raw(collection):
            try:
                items.append(model.model_validate(record))
            except ValidationError:
                continue
        return items

    def get(self, collection: str, item_id: str) -> T | None:
        for item in self.list(collection):
            if item.id == item_id:
                return item
        return None

    def latest(self, collection: str) -> T | None:
        items = self.list(collection)
        if not items:
            return None
        return sorted(items, key=lambda item: item.created_at)[-1]

    def save(self, collection: str, item: T) -> T:
        with _STORE_LOCK:
            records = self._read_raw(collection)
            serialized = item.model_dump(mode="json")
            records = [record for record in records if record.get("id") != item.id]
            records.append(serialized)
            self._write_raw(collection, records)
        return item

    def append_event(self, event: RunEvent) -> RunEvent:
        return self.save("events", event)

    def events_for_run(self, run_id: str) -> list[RunEvent]:
        return [event for event in self.list("events") if event.run_id == run_id]

    def runtime_settings(self) -> RuntimeSettings:
        return self.get("runtime", "runtime") or self.save(
            "runtime",
            runtime_from_settings(self.settings),
        )
