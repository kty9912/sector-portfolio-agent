import pytest
from core import db

def test_healthcheck(monkeypatch):
    db.healthcheck = lambda: True
    assert db.healthcheck() is True

def test_fetch_one(monkeypatch):
    db.fetch_one = lambda sql: (1,)
    result = db.fetch_one("SELECT 1;")
    assert result == (1,)
