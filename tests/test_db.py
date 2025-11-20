import pytest
from core.db import healthcheck, fetch_one, exec_sql

def test_healthcheck():
    assert healthcheck() is True

def test_fetch_one():
    result = fetch_one("SELECT 1;")
    assert result == (1,)
