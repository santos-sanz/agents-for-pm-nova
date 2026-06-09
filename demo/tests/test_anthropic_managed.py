from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from hyper_demo.adapters.anthropic_managed import (
    CHAT_MEMORY_STORE_NAMES,
    RESEARCH_AGENT_NAME,
    RESEARCH_ENVIRONMENT_NAME,
    ManagedAgentResearchClient,
    _duplicates_to_remove,
)
from hyper_demo.config import Settings
from hyper_demo.services.managed_chat import ManagedTradingChatService, _find_latest_named_resource
from hyper_demo.storage import JsonStore


class FakeListApi:
    def __init__(self, items: list[SimpleNamespace]) -> None:
        self.items = items
        self.created: list[dict] = []

    def list(self, limit: int = 100) -> SimpleNamespace:
        return SimpleNamespace(data=self.items)

    def create(self, **payload) -> SimpleNamespace:
        self.created.append(payload)
        item = SimpleNamespace(
            id=f"created_{len(self.created)}",
            name=payload["name"],
            created_at="2026-06-10T00:00:00Z",
            version=1,
        )
        self.items.append(item)
        return item


def test_research_resources_reuse_latest_matching_agent_and_environment(tmp_path) -> None:
    settings = Settings(
        DEMO_STATE_DIR=tmp_path,
        ANTHROPIC_API_KEY=SecretStr("test-key"),
        ANTHROPIC_AGENT_ID="",
        ANTHROPIC_ENVIRONMENT_ID="",
    )
    store = JsonStore(settings)
    environments = FakeListApi(
        [
            SimpleNamespace(
                id="env_old",
                name=RESEARCH_ENVIRONMENT_NAME,
                created_at="2026-06-01T00:00:00Z",
            ),
            SimpleNamespace(
                id="env_new",
                name=RESEARCH_ENVIRONMENT_NAME,
                created_at="2026-06-02T00:00:00Z",
            ),
        ]
    )
    agents = FakeListApi(
        [
            SimpleNamespace(
                id="agent_old",
                name=RESEARCH_AGENT_NAME,
                created_at="2026-06-01T00:00:00Z",
                version=1,
            ),
            SimpleNamespace(
                id="agent_new",
                name=RESEARCH_AGENT_NAME,
                created_at="2026-06-02T00:00:00Z",
                version=3,
            ),
        ]
    )
    remote = SimpleNamespace(beta=SimpleNamespace(environments=environments, agents=agents))

    resources = ManagedAgentResearchClient(settings, store)._research_resources(remote)

    assert resources.environment_id == "env_new"
    assert resources.agent_id == "agent_new"
    assert resources.agent_version == 3
    assert environments.created == []
    assert agents.created == []
    persisted = store.get("managed_agent_research_resources", "managed_agent_research_resources")
    assert persisted
    assert persisted.agent_id == "agent_new"


def test_duplicates_to_remove_keeps_newest_matching_resources() -> None:
    items = [
        SimpleNamespace(id="old", name=RESEARCH_AGENT_NAME, created_at="2026-06-01T00:00:00Z"),
        SimpleNamespace(id="new", name=RESEARCH_AGENT_NAME, created_at="2026-06-02T00:00:00Z"),
        SimpleNamespace(id="other", name="unrelated", created_at="2026-06-03T00:00:00Z"),
    ]

    removed = _duplicates_to_remove(items, RESEARCH_AGENT_NAME, keep=1)

    assert [item.id for item in removed] == ["old"]


def test_chat_resource_lookup_filters_by_metadata_and_keeps_latest() -> None:
    api = FakeListApi(
        [
            SimpleNamespace(
                id="agent_wrong_role",
                name="HyperClaude Research Agent",
                created_at="2026-06-03T00:00:00Z",
                metadata={"app": "hyperclaude", "role": "risk"},
            ),
            SimpleNamespace(
                id="agent_old",
                name="HyperClaude Research Agent",
                created_at="2026-06-01T00:00:00Z",
                metadata={"app": "hyperclaude", "role": "research"},
            ),
            SimpleNamespace(
                id="agent_new",
                name="HyperClaude Research Agent",
                created_at="2026-06-02T00:00:00Z",
                metadata={"app": "hyperclaude", "role": "research"},
            ),
        ]
    )

    resource = _find_latest_named_resource(
        api,
        "HyperClaude Research Agent",
        metadata={"app": "hyperclaude", "role": "research"},
    )

    assert resource
    assert resource.id == "agent_new"


def test_chat_memory_stores_reuse_existing_latest_stores(tmp_path) -> None:
    settings = Settings(DEMO_STATE_DIR=tmp_path)
    service = ManagedTradingChatService(JsonStore(settings), settings)
    memory_stores = FakeListApi(
        [
            SimpleNamespace(
                id="canon_old",
                name="HyperClaude Trading Canon",
                created_at="2026-06-01T00:00:00Z",
                metadata={"app": "hyperclaude", "kind": "canon"},
            ),
            SimpleNamespace(
                id="canon_new",
                name="HyperClaude Trading Canon",
                created_at="2026-06-02T00:00:00Z",
                metadata={"app": "hyperclaude", "kind": "canon"},
            ),
            SimpleNamespace(
                id="learning_new",
                name="HyperClaude Conversation Learning",
                created_at="2026-06-02T00:00:00Z",
                metadata={"app": "hyperclaude", "kind": "learning"},
            ),
        ]
    )
    memories = SimpleNamespace(create=lambda *args, **kwargs: None)
    remote = SimpleNamespace(
        beta=SimpleNamespace(
            memory_stores=SimpleNamespace(
                list=memory_stores.list,
                create=memory_stores.create,
                memories=memories,
            )
        )
    )

    ids = service._create_memory_stores(remote)

    assert ids == {"canon": "canon_new", "learning": "learning_new"}
    assert memory_stores.created == []


def test_memory_store_duplicates_keep_newest_per_store_name() -> None:
    items = [
        SimpleNamespace(
            id="canon_old",
            name=CHAT_MEMORY_STORE_NAMES[0],
            created_at="2026-06-01T00:00:00Z",
        ),
        SimpleNamespace(
            id="canon_new",
            name=CHAT_MEMORY_STORE_NAMES[0],
            created_at="2026-06-02T00:00:00Z",
        ),
        SimpleNamespace(
            id="learning_old",
            name=CHAT_MEMORY_STORE_NAMES[1],
            created_at="2026-06-01T00:00:00Z",
        ),
        SimpleNamespace(
            id="learning_new",
            name=CHAT_MEMORY_STORE_NAMES[1],
            created_at="2026-06-02T00:00:00Z",
        ),
    ]

    removed = [
        item
        for name in CHAT_MEMORY_STORE_NAMES
        for item in _duplicates_to_remove(items, name, keep=1)
    ]

    assert [item.id for item in removed] == ["canon_old", "learning_old"]
