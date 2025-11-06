# experiments/calc_signals_latest.py
import pandas as pd
import numpy as np
from core.db import fetch_all, exec_sql, exec_many

# ─────────────────────────────────────────────────────────
# 테이블 준비: calculated_at 자동 기록 컬럼 포함
# ─────────────────────────────────────────────────────────
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS signals_latest (
  ticker TEXT PRIMARY KEY,
  asof DATE NOT NULL,
  ma20 NUMERIC,
  ma60 NUMERIC,
  rsi14 NUMERIC,
  atr14 NUMERIC,
  momentum_20d NUMERIC,
  vol_20d NUMERIC,
  calculated_at TIMESTAMP DEFAULT NOW()
);
"""

UPSERT_SQL = """
INSERT INTO signals_latest
(ticker, asof, ma20, ma60, rsi14, atr14, momentum_20d, vol_20d, calculated_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
ON CONFLICT (ticker) DO UPDATE SET
  asof=EXCLUDED.asof,
  ma20=EXCLUDED.ma20,
  ma60=EXCLUDED.ma60,
  rsi14=EXCLUDED.rsi14,
  atr14=EXCLUDED.atr14,
  momentum_20d=EXCLUDED.momentum_20d,
  vol_20d=EXCLUDED.vol_20d,
  calculated_at=NOW();
"""

def ensure_table():
    exec_sql(CREATE_TABLE)

# ─────────────────────────────────────────────────────────
# 지표 계산 함수
# ─────────────────────────────────────────────────────────
def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    # TR = max(high-low, |high-prev_close|, |low-prev_close|)
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()

def _calc_one(ticker: str) -> tuple | None:
    # 최근 데이터 불러오기 (필요 컬럼만)
    rows = fetch_all(
        """
        SELECT date, open, high, low, close
        FROM prices_daily
        WHERE ticker=%s
        ORDER BY date
        """,
        (ticker,)
    )
    if not rows or len(rows) < 60:
        return None  # MA60 계산 위해 최소 60개 필요

    df = pd.DataFrame(rows, columns=["date","open","high","low","close"]).astype({
        "open": float, "high": float, "low": float, "close": float
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # 이동평균
    df["ma20"] = df["close"].rolling(20, min_periods=20).mean()
    df["ma60"] = df["close"].rolling(60, min_periods=60).mean()

    # RSI14, ATR14
    df["rsi14"] = _rsi(df["close"], 14)
    df["atr14"] = _atr(df, 14)

    # 모멘텀/변동성(표준편차)
    df["momentum_20d"] = df["close"] / df["close"].shift(20) - 1.0
    df["vol_20d"] = df["close"].rolling(20, min_periods=20).std()

    last = df.iloc[-1]
    if pd.isna(last[["ma20","ma60","rsi14","atr14","momentum_20d","vol_20d"]]).all():
        return None

    # asof = 최신 가격 날짜
    return (
        ticker,
        last["date"].date(),
        None if pd.isna(last["ma20"]) else float(last["ma20"]),
        None if pd.isna(last["ma60"]) else float(last["ma60"]),
        None if pd.isna(last["rsi14"]) else float(last["rsi14"]),
        None if pd.isna(last["atr14"]) else float(last["atr14"]),
        None if pd.isna(last["momentum_20d"]) else float(last["momentum_20d"]),
        None if pd.isna(last["vol_20d"]) else float(last["vol_20d"]),
    )

def main():
    ensure_table()

    print("📊 signals_latest 계산 시작")

    # 활성 종목만 대상 (companies 기준) + prices가 존재하는 종목
    tickers = [r[0] for r in fetch_all(
        """
        SELECT c.ticker
        FROM companies c
        WHERE c.is_active = TRUE
          AND EXISTS (SELECT 1 FROM prices_daily p WHERE p.ticker = c.ticker)
        ORDER BY c.ticker
        """
    )]
    print('tickers', tickers)

    upserts = []
    for t in tickers:
        try:
            row = _calc_one(t)
            if row:
                upserts.append(row)
        except Exception as e:
            print(f"⚠️ {t} 계산 실패: {e}")

    if upserts:
        exec_many(UPSERT_SQL, upserts)
    print(f"✅ 완료: {len(upserts)} 종목 업데이트")

if __name__ == "__main__":
    main()
