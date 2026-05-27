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
