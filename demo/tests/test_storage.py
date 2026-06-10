from hyper_demo.config import Settings
from hyper_demo.models import RiskProfileInput
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.storage import JsonStore


def test_store_recovers_from_corrupt_json(tmp_path) -> None:
    store = JsonStore(Settings(DEMO_STATE_DIR=tmp_path))
    (tmp_path / "profiles.json").write_text("{not-json", encoding="utf-8")

    assert store.list("profiles") == []


def test_store_atomic_save_after_corrupt_json(tmp_path) -> None:
    store = JsonStore(Settings(DEMO_STATE_DIR=tmp_path))
    (tmp_path / "profiles.json").write_text("{not-json", encoding="utf-8")
    profile = build_investor_profile(RiskProfileInput())

    store.save("profiles", profile)

    assert store.get("profiles", profile.id) == profile


def test_store_deletes_record(tmp_path) -> None:
    store = JsonStore(Settings(DEMO_STATE_DIR=tmp_path))
    profile = build_investor_profile(RiskProfileInput())
    store.save("profiles", profile)

    assert store.delete("profiles", profile.id) is True
    assert store.get("profiles", profile.id) is None
    assert store.delete("profiles", profile.id) is False


def test_store_skips_records_that_no_longer_match_schema(tmp_path) -> None:
    store = JsonStore(Settings(DEMO_STATE_DIR=tmp_path))
    legacy_exchange = "".join(["pa", "per", "-", "coin", "base"])
    (tmp_path / "orders.json").write_text(
        '[{"id":"order_old","created_at":"2026-01-01T00:00:00Z","plan_id":"plan_old",'
        f'"exchange":"{legacy_exchange}","asset":"BTC","side":"long","size_usdc":100,'
        '"raw_response":{},"status":"simulated","message":"old"}]',
        encoding="utf-8",
    )

    assert store.list("orders") == []
