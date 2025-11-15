import os
import time
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from pykrx import stock
from core.db import exec_many, exec_sql, fetch_all

# ------------------------------
#  환경 설정
# ------------------------------
CERT_PATH = r"C:\certs\cacert.pem"
if os.path.exists(CERT_PATH):
    os.environ['CURL_CA_BUNDLE'] = CERT_PATH
    os.environ['SSL_CERT_FILE'] = CERT_PATH
    os.environ['REQUESTS_CA_BUNDLE'] = CERT_PATH
else:
    print(f"⚠️ 경고: {CERT_PATH} 파일이 없습니다. yfinance가 작동하지 않을 수 있습니다.")
    print("해결: python experiments/fix_cert_path.py 실행")

# 화이트리스트
TICKERS = [r[0] for r in fetch_all("SELECT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker;")]

START = (date.today() - timedelta(days=365 * 5)).isoformat()
END = None  # 오늘까지

# ------------------------------
#  prices_daily 테이블 생성 (없으면)
# ------------------------------
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS prices_daily (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    adj_close NUMERIC,
    volume BIGINT,
    etl_loaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (ticker, date)
);
"""

# ------------------------------
#  업서트 쿼리 (etl_loaded_at 자동 갱신 포함)
# ------------------------------
UPSERT_SQL = """
INSERT INTO prices_daily
(ticker, date, open, high, low, close, adj_close, volume, etl_loaded_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
ON CONFLICT (ticker, date) DO UPDATE SET
  open=EXCLUDED.open,
  high=EXCLUDED.high,
  low=EXCLUDED.low,
  close=EXCLUDED.close,
  adj_close=EXCLUDED.adj_close,
  volume=EXCLUDED.volume,
  etl_loaded_at=NOW();
"""

def ensure_table():
    exec_sql(CREATE_TABLE)

# ------------------------------
#  데이터 로더
# ------------------------------
def fetch_yfinance(ticker: str):
    """yfinance에서 시세 수집"""
    try:
        df = yf.download(
            ticker, start=START, end=END,
            interval="1d", auto_adjust=False,
            threads=False, progress=False
        )
        if df.empty:
            return None
        df = df.reset_index()
        df.rename(columns=str.lower, inplace=True)
        df["ticker"] = ticker
        df.rename(columns={"adj close": "adj_close"}, inplace=True)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]]
    except Exception as e:
        print(f"⚠️ [yfinance] {ticker} 실패: {e}")
        return None


def fetch_pykrx(ticker: str):
    """yfinance 실패 시 pykrx로 fallback"""
    try:
        code = ticker.split(".")[0]
        df = stock.get_market_ohlcv_by_date("20200101", date.today().strftime("%Y%m%d"), code)
        if df.empty:
            return None
        df.reset_index(inplace=True)
        df["ticker"] = ticker
        df.rename(columns={
            "시가": "open", "고가": "high", "저가": "low",
            "종가": "close", "거래량": "volume"
        }, inplace=True)
        df["adj_close"] = df["close"]  # pykrx에는 조정가 없음
        df["date"] = pd.to_datetime(df["날짜"]).dt.date
        return df[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]]
    except Exception as e:
        print(f"⚠️ [pykrx] {ticker} 실패: {e}")
        return None

# ------------------------------
#  업서트 실행
# ------------------------------
def upsert_prices(df: pd.DataFrame):
    if df is None or df.empty:
        return
    rows = [tuple(x) for x in df.to_numpy()]
    exec_many(UPSERT_SQL, rows)

# ------------------------------
#  전체 실행
# ------------------------------
def main():
    print("📈 prices_daily 업데이트 시작")
    ensure_table()

    success, fail = 0, []
    for t in TICKERS:
        df = fetch_yfinance(t)
        if df is None or df.empty:
            print(f"🔄 yfinance 실패 → pykrx 시도: {t}")
            df = fetch_pykrx(t)
        if df is None or df.empty:
            print(f"❌ {t} 데이터 없음")
            fail.append(t)
            continue
        upsert_prices(df)
        success += 1
        print(f"✅ {t} ({len(df)} rows)")
        time.sleep(1.5)  # API 과부하 방지

    print(f"🎯 완료: {success} 성공, {len(fail)} 실패")
    if fail:
        print("실패 티커:", fail)


if __name__ == "__main__":
    main()
