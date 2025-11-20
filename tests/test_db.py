import pytest
from core.db import healthcheck, fetch_one, exec_sql

def test_healthcheck():
    assert healthcheck() is True

def test_fetch_one():
    result = fetch_one("SELECT 1;")
    assert result == (1,)

# DB에 쓰기 테스트는 실제 환경에 따라 주석 처리 또는 별도 관리 필요
# def test_exec_sql():
#     rowcount = exec_sql("CREATE TABLE IF NOT EXISTS test_table (id INT);")
#     assert isinstance(rowcount, int)
    assert result == 1
