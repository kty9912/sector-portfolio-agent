from core.db import fetch_all, exec_sql

# 테이블 없으면 만들어보기(테스트용)
exec_sql("""
CREATE TABLE IF NOT EXISTS _env_check (
  k TEXT PRIMARY KEY,
  v TEXT
);
""")

# upsert 예시
exec_sql("""
INSERT INTO _env_check (k, v)
VALUES ('hello','world')
ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v;
""")

ALTERS = ["ALTER TABLE prices_daily   ADD COLUMN IF NOT EXISTS etl_loaded_at TIMESTAMP DEFAULT NOW();"]

if __name__ == "__main__":
    for sql in ALTERS:
        exec_sql(sql)
    print("✅ timestamp 컬럼 추가 완료")