# core/db.py
from __future__ import annotations
import os
from typing import Any, Iterable, Sequence, Tuple, Optional
import psycopg2
import psycopg2.extras as _extras
from dotenv import load_dotenv, find_dotenv

# ── .env 로드 (어디서 실행하든 루트 .env를 찾도록)
load_dotenv(find_dotenv(usecwd=True))

DB_CFG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "finlab"),
    "user": os.getenv("DB_USER", "finuser"),
    "password": os.getenv("DB_PASS", ""),
}

def get_conn():
    """psycopg2 연결 생성자 (호출한 쪽에서 close 책임)"""
    return psycopg2.connect(**DB_CFG)

# ── 편의 함수들(ORM 없이 순수 SQL)
def exec_sql(sql: str, params: Optional[Sequence[Any]] = None) -> int:
    """INSERT/UPDATE/DELETE/DDL. 적용된 rowcount 반환"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.rowcount

def exec_many(sql: str, rows: Iterable[Sequence[Any]]) -> int:
    """executemany 업서트 등 대량 처리"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, list(rows))
        return cur.rowcount

def fetch_all(sql: str, params: Optional[Sequence[Any]] = None) -> list[Tuple[Any, ...]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.fetchall()

def fetch_dicts(sql: str, params: Optional[Sequence[Any]] = None) -> list[dict]:
    """dict 형태로 가져오기 (컬럼명 포함)"""
    with get_conn() as conn, conn.cursor(cursor_factory=_extras.RealDictCursor) as cur:
        cur.execute(sql, params or None)
        return [dict(r) for r in cur.fetchall()]

def fetch_one(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[Tuple[Any, ...]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.fetchone()

def healthcheck() -> bool:
    try:
        return fetch_one("SELECT 1;")[0] == 1
    except Exception:
        return False

# ── CLI: `python -m core.db ping` 같은 빠른 점검용
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ping"
    if cmd == "ping":
        ok = healthcheck()
        print("DB OK" if ok else "DB FAIL", DB_CFG)
    elif cmd == "tables":
        rows = fetch_all("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;")
        print([r[0] for r in rows])
    else:
        print("Usage: python -m core.db [ping|tables]")
