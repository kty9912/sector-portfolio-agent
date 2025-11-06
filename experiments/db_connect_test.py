import os
import psycopg2
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from dotenv import load_dotenv
from core.db import fetch_all

load_dotenv()

DB = dict(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT', "5432"),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASS')
)

# 화이트리스트(YF 티커)
TICKERS = [r[0] for r in fetch_all("SELECT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker;")]

START = (date.today() - timedelta(days=365*2)).isoformat()  # 최근 2년
END   = None  # 오늘까지

print('start :', START)
print('end :', END)

def get_conn():
    return psycopg2.connect(**DB)

def ensure_table():
    sql = """
    CREATE TABLE IF NOT EXISTS prices_daily (
        ticker   TEXT NOT NULL,
        date     DATE NOT NULL,
        open     NUMERIC,
        high     NUMERIC,
        low      NUMERIC,
        close    NUMERIC,
        adj_close NUMERIC,
        volume   BIGINT,
        PRIMARY KEY (ticker, date)
    );
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()

def fetch_prices(tickers):
    df = yf.download(
        tickers, start=START, end=END, interval="1d",
        group_by="ticker", auto_adjust=False, threads=True
    )
    rows = []
    if isinstance(tickers, str):  # 단일 티커 형태 방지
        tickers = [tickers]
    for t in tickers:
        sub = df[t].reset_index().rename(columns=str.lower)
        sub["ticker"] = t
        # NaN → None
        sub = sub[["ticker","date","open","high","low","close","adj close","volume"]]
        sub = sub.rename(columns={"adj close":"adj_close"})
        for _, r in sub.iterrows():
            rows.append((
                r["ticker"], r["date"].date() if hasattr(r["date"], "date") else r["date"],
                None if pd.isna(r["open"]) else float(r["open"]),
                None if pd.isna(r["high"]) else float(r["high"]),
                None if pd.isna(r["low"]) else float(r["low"]),
                None if pd.isna(r["close"]) else float(r["close"]),
                None if pd.isna(r["adj_close"]) else float(r["adj_close"]),
                None if pd.isna(r["volume"]) else int(r["volume"])
            ))
    return rows

UPSERT_SQL = """
INSERT INTO prices_daily
(ticker, date, open, high, low, close, adj_close, volume)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (ticker, date) DO UPDATE SET
  open = EXCLUDED.open,
  high = EXCLUDED.high,
  low  = EXCLUDED.low,
  close= EXCLUDED.close,
  adj_close = EXCLUDED.adj_close,
  volume = EXCLUDED.volume;
"""

def upsert_prices(rows, batch=1000):
    with get_conn() as conn, conn.cursor() as cur:
        for i in range(0, len(rows), batch):
            cur.executemany(UPSERT_SQL, rows[i:i+batch])
        conn.commit()

if __name__ == "__main__":
    ensure_table()
    data = fetch_prices(TICKERS)
    print(f"다운로드 행수: {len(data)}")
    upsert_prices(data)
    print("업서트 완료!")
