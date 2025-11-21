import pytest
import pytest
from core.db import healthcheck, fetch_one, exec_sql
from core.db import healthcheck, fetch_one, exec_sql

def test_healthcheck(monkeypatch):
    monkeypatch.setattr("core.db.healthcheck", lambda: True)
    assert healthcheck() is True

def test_fetch_one(monkeypatch):
    monkeypatch.setattr("core.db.fetch_one", lambda sql: (1,))
    result = fetch_one("SELECT 1;")
    assert result == (1,)
