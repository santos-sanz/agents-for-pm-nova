from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from hyper_demo.adapters.anthropic_managed import (
    CHAT_MEMORY_STORE_NAMES,
    CHAT_SKILL_TITLES,
    RESEARCH_AGENT_NAME,
    RESEARCH_ENVIRONMENT_NAME,
    ManagedAgentResearchClient,
    _delete_skill_with_versions,
    _duplicates_to_remove,
    _skill_duplicates_to_remove,
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


class FakeSkillVersionsApi:
    def __init__(self) -> None:
        self.deleted_versions: list[tuple[str, str]] = []

    def list(self, skill_id: str, limit: int = 100) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(version=1), SimpleNamespace(version=2)])

    def delete(self, version: str, *, skill_id: str) -> None:
        self.deleted_versions.append((skill_id, version))


class FakeSkillsApi:
    def __init__(self) -> None:
        self.versions = FakeSkillVersionsApi()
        self.deleted_skills: list[str] = []

    def delete(self, skill_id: str) -> None:
        self.deleted_skills.append(skill_id)


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
    service = ManagedTradingChatService(settings, JsonStore(settings))
    memory_stores = FakeListApi(
        [
            SimpleNamespace(
                id="canon_old",
                name="Nova Wealth Guard Canon",
                created_at="2026-06-01T00:00:00Z",
                metadata={"app": "nova-wealth-guard", "kind": "canon"},
            ),
            SimpleNamespace(
                id="canon_new",
                name="Nova Wealth Guard Canon",
                created_at="2026-06-02T00:00:00Z",
                metadata={"app": "nova-wealth-guard", "kind": "canon"},
            ),
            SimpleNamespace(
                id="learning_new",
                name="Nova Wealth Guard Conversation Learning",
                created_at="2026-06-02T00:00:00Z",
                metadata={"app": "nova-wealth-guard", "kind": "learning"},
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


def test_skill_duplicates_keep_newest_matching_base_title() -> None:
    items = [
        SimpleNamespace(
            id="skill_old",
            display_title=f"{CHAT_SKILL_TITLES[0]} (managed-chat-old)",
            created_at="2026-06-01T00:00:00Z",
        ),
        SimpleNamespace(
            id="skill_new",
            display_title=CHAT_SKILL_TITLES[0],
            created_at="2026-06-02T00:00:00Z",
        ),
        SimpleNamespace(
            id="skill_other",
            display_title="Unrelated Skill",
            created_at="2026-06-03T00:00:00Z",
        ),
    ]

    removed = _skill_duplicates_to_remove(items, CHAT_SKILL_TITLES[0], keep=1)

    assert [item.id for item in removed] == ["skill_old"]


def test_chat_skills_reuse_existing_latest_titles(tmp_path) -> None:
    settings = Settings(DEMO_STATE_DIR=tmp_path)
    service = ManagedTradingChatService(settings, JsonStore(settings))
    skills = FakeListApi(
        [
            SimpleNamespace(
                id=f"skill_{index}",
                display_title=title,
                created_at=f"2026-06-0{index + 1}T00:00:00Z",
                version=index + 1,
            )
            for index, title in enumerate(CHAT_SKILL_TITLES)
        ]
    )
    remote = SimpleNamespace(beta=SimpleNamespace(skills=skills))

    skill_ids, skill_versions = service._create_skills(remote)

    assert set(skill_ids) == {
        "hyperliquid-safety",
        "source-quality",
        "hypertracker-cli",
        "trade-validation",
        "formal-order-validation",
        "self-improvement",
    }
    assert skill_ids["hyperliquid-safety"] == "skill_0"
    assert skill_versions["self-improvement"] == 6
    assert skills.created == []


def test_managed_vault_id_reuses_remote_vault_when_local_state_missing(tmp_path) -> None:
    settings = Settings(DEMO_STATE_DIR=tmp_path)
    service = ManagedTradingChatService(settings, JsonStore(settings))
    vaults = FakeListApi(
        [
            SimpleNamespace(
                id="vault_old",
                display_name="Nova Wealth Guard API-Key Tools",
                created_at="2026-06-01T00:00:00Z",
                metadata={"app": "nova-wealth-guard", "component": "nova-wealth-guard"},
            ),
            SimpleNamespace(
                id="vault_new",
                display_name="Nova Wealth Guard API-Key Tools",
                created_at="2026-06-02T00:00:00Z",
                metadata={"app": "nova-wealth-guard", "component": "nova-wealth-guard"},
            ),
        ]
    )
    remote = SimpleNamespace(beta=SimpleNamespace(vaults=vaults))

    vault_id = service._managed_vault_id(remote)

    assert vault_id == "vault_new"
    assert vaults.created == []


def test_delete_skill_removes_versions_first() -> None:
    skills = FakeSkillsApi()
    client = SimpleNamespace(beta=SimpleNamespace(skills=skills))

    _delete_skill_with_versions(client, "skill_demo")

    assert skills.versions.deleted_versions == [
        ("skill_demo", "1"),
        ("skill_demo", "2"),
    ]
    assert skills.deleted_skills == ["skill_demo"]
