import urllib.error

import pytest

from hyper_demo.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch):
    def offline_urlopen(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "false")
    monkeypatch.setattr("urllib.request.urlopen", offline_urlopen)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
