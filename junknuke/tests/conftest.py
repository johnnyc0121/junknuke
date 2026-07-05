"""
pytest configuration and shared fixtures for JunkNuke tests.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """
    Provide safe default settings for all tests so no real
    env vars or config files are needed to run the suite.
    """
    import junknuke.settings as settings
    monkeypatch.setenv("AZURE_CLIENT_ID", "mock-client-id-for-testing")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "mock-client-secret-for-testing")
    monkeypatch.setattr(settings, "INFLUX_URL",    "http://localhost:8086")
    monkeypatch.setattr(settings, "INFLUX_ORG",    "junknuke")
    monkeypatch.setattr(settings, "INFLUX_BUCKET", "messages")
    monkeypatch.setattr(settings, "DATA_DIR",      "/tmp/junknuke_test")
    monkeypatch.setattr(settings, "ALLOWLIST",     [])
    monkeypatch.setattr(settings, "ENABLE_GEOTRACK", True)
    monkeypatch.setattr(settings, "DELETE_AFTER_UNSUB", True)
    monkeypatch.setattr(settings, "DELETE_IF_NO_UNSUB", True)
    monkeypatch.setattr(settings, "MIN_AGE_DAYS",  1)
    monkeypatch.setattr(settings, "REQUEST_DELAY_SECONDS", 0)
