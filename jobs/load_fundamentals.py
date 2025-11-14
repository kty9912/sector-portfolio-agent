import os
import pandas as pd
import yfinance as yf
from core.db import exec_sql, exec_many, fetch_all

# --- 한글 경로 문제 해결: 인증서 경로 설정 ---
CERT_PATH = r"C:\certs\cacert.pem"
if os.path.exists(CERT_PATH):
    os.environ['CURL_CA_BUNDLE'] = CERT_PATH
    os.environ['SSL_CERT_FILE'] = CERT_PATH
    os.environ['REQUESTS_CA_BUNDLE'] = CERT_PATH
else:
    print(f"⚠️ 경고: {CERT_PATH} 파일이 없습니다. yfinance가 작동하지 않을 수 있습니다.")
    print("해결: python experiments/fix_cert_path.py 실행")

# --- 테이블 생성 (없으면) ---
CREATE_FUNDAMENTALS = """
CREATE TABLE IF NOT EXISTS fundamentals (
  ticker        TEXT NOT NULL,
  fiscal_date   DATE NOT NULL,
  freq          CHAR(1) NOT NULL,            -- 'A' 연간, 'Q' 분기
  revenue       NUMERIC,
  op_income     NUMERIC,
  net_income    NUMERIC,
  total_assets  NUMERIC,
  total_liab    NUMERIC,
  equity        NUMERIC,
  ebitda        NUMERIC,
  cash_from_ops NUMERIC,
  capex         NUMERIC,
  etl_loaded_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (ticker, fiscal_date, freq)
);
"""
CREATE_METRICS = """
CREATE TABLE IF NOT EXISTS fin_metrics (
  ticker        TEXT NOT NULL,
  fiscal_date   DATE NOT NULL,
  freq          CHAR(1) NOT NULL,
  roe           NUMERIC,
  opm           NUMERIC,
  debt_ratio    NUMERIC,
  roa           NUMERIC,
  rev_growth_yoy NUMERIC,
  fcf           NUMERIC,
  etl_loaded_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (ticker, fiscal_date, freq)
);
"""

UPSERT_FUND = """
INSERT INTO fundamentals
(ticker,fiscal_date,freq,revenue,op_income,net_income,total_assets,total_liab,equity,ebitda,cash_from_ops,capex,etl_loaded_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
ON CONFLICT (ticker,fiscal_date,freq) DO UPDATE SET
  revenue       = COALESCE(EXCLUDED.revenue,       fundamentals.revenue),
  op_income     = COALESCE(EXCLUDED.op_income,     fundamentals.op_income),
  net_income    = COALESCE(EXCLUDED.net_income,    fundamentals.net_income),
  total_assets  = COALESCE(EXCLUDED.total_assets,  fundamentals.total_assets),
  total_liab    = COALESCE(EXCLUDED.total_liab,    fundamentals.total_liab),
  equity        = COALESCE(EXCLUDED.equity,        fundamentals.equity),
  ebitda        = COALESCE(EXCLUDED.ebitda,        fundamentals.ebitda),
  cash_from_ops = COALESCE(EXCLUDED.cash_from_ops, fundamentals.cash_from_ops),
  capex         = COALESCE(EXCLUDED.capex,         fundamentals.capex),
  etl_loaded_at = NOW();
"""

UPSERT_METRICS = """
INSERT INTO fin_metrics
(ticker,fiscal_date,freq,roe,opm,debt_ratio,roa,rev_growth_yoy,fcf,etl_loaded_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
ON CONFLICT (ticker,fiscal_date,freq) DO UPDATE SET
  roe            = COALESCE(EXCLUDED.roe,            fin_metrics.roe),
  opm            = COALESCE(EXCLUDED.opm,            fin_metrics.opm),
  debt_ratio     = COALESCE(EXCLUDED.debt_ratio,     fin_metrics.debt_ratio),
  roa            = COALESCE(EXCLUDED.roa,            fin_metrics.roa),
  rev_growth_yoy = COALESCE(EXCLUDED.rev_growth_yoy, fin_metrics.rev_growth_yoy),
  fcf            = COALESCE(EXCLUDED.fcf,            fin_metrics.fcf),
  etl_loaded_at  = NOW();
"""

def ensure_table():
    exec_sql(CREATE_FUNDAMENTALS)
    exec_sql(CREATE_METRICS)

def _to_float(x):
    if x is None:
        return None
    try:
        import math
        if isinstance(x, (float, int)) and (x != x or math.isinf(x)):  # NaN/inf
            return None
    except Exception:
        pass
    try:
        # pandas/Decimal/NumPy 전부 안전 변환
        return float(x)
    except Exception:
        return None

def _extract_blocks(tkr: yf.Ticker, quarterly=False):
    rows = []
    if quarterly:
        fin = getattr(tkr, "quarterly_financials", pd.DataFrame())
        bs  = getattr(tkr, "quarterly_balance_sheet", pd.DataFrame())
        cf  = getattr(tkr, "quarterly_cashflow", pd.DataFrame())
        freq = "Q"
    else:
        fin = getattr(tkr, "financials", pd.DataFrame())
        bs  = getattr(tkr, "balance_sheet", pd.DataFrame())
        cf  = getattr(tkr, "cashflow", pd.DataFrame())
        freq = "A"

    if fin is None or fin.empty or bs is None or bs.empty:
        return rows

    fin = fin.transpose()
    bs  = bs.transpose()
    cf  = cf.transpose() if cf is not None else pd.DataFrame()

    # 연간: 최근 4년, 분기: 최근 16분기
    period_count = 16 if quarterly else 4
    for idx in list(fin.index)[-period_count:]:
        def get(df, key):
            try: return df.loc[idx, key]
            except Exception: return None
        
        # 다중 필드명 시도 (yfinance 필드명 변경 대응)
        def get_multi(df, *keys):
            for key in keys:
                val = get(df, key)
                if val is not None:
                    return val
            return None

        rows.append(dict(
            fiscal_date = pd.to_datetime(idx).date(),
            freq = freq,
            revenue = _to_float(get(fin, "Total Revenue")),
            op_income = _to_float(get(fin, "Operating Income")),
            net_income = _to_float(get(fin, "Net Income")),
            ebitda = _to_float(get(fin, "EBITDA")),
            total_assets = _to_float(get(bs, "Total Assets")),
            total_liab   = _to_float(get_multi(bs, "Total Liabilities Net Minority Interest", "Total Liab")),
            equity       = _to_float(get_multi(bs, "Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity")),
            cash_from_ops = _to_float(get_multi(cf, "Operating Cash Flow", "Total Cash From Operating Activities")) if not cf.empty else None,
            capex         = _to_float(get_multi(cf, "Capital Expenditure", "Capital Expenditures")) if not cf.empty else None,
        ))
    return rows

def _calc_metrics(row, prev_row=None):
    eq = row.get("equity") or 0.0
    assets = row.get("total_assets") or 0.0
    ni = row.get("net_income")
    op = row.get("op_income")
    rev = row.get("revenue")
    liab = row.get("total_liab")

    roe = (ni / eq) if (ni is not None and eq not in (None, 0)) else None
    roa = (ni / assets) if (ni is not None and assets not in (None, 0)) else None
    opm = (op / rev) if (op is not None and rev not in (None, 0)) else None
    debt_ratio = (liab / eq) if (liab not in (None, 0) and eq not in (None, 0)) else None

    fcf = None
    cfo = row.get("cash_from_ops")
    capex = row.get("capex")
    if cfo is not None and capex is not None:
        fcf = cfo - capex

    rev_growth_yoy = None
    if prev_row and row["freq"] == prev_row["freq"]:
        prev_rev = prev_row.get("revenue")
        if rev is not None and prev_rev not in (None, 0):
            rev_growth_yoy = (rev - prev_rev) / prev_rev

    return dict(roe=roe, opm=opm, debt_ratio=debt_ratio, roa=roa, rev_growth_yoy=rev_growth_yoy, fcf=fcf)

def main():
    ensure_table()

    print("📑 fundamentals/fin_metrics 적재 시작")

    # 활성 티커만
    tickers = [r[0] for r in fetch_all(
        "SELECT ticker FROM companies WHERE is_active=TRUE ORDER BY ticker;"
    )]

    fund_rows, met_rows = [], []

    for t in tickers:
        try:
            tk = yf.Ticker(t)
            rows = []
            # 연간 + 분기 가져오기 (둘 다 시도)
            rows += _extract_blocks(tk, quarterly=False)
            rows += _extract_blocks(tk, quarterly=True)
            if not rows:
                print(f"⚠️ {t}: fundamentals 없음(일시적일 수 있음)")
                continue

            # (date,freq) 중복 제거 + 정렬
            uniq = {}
            for r in rows:
                uniq[(r["fiscal_date"], r["freq"])] = r
            rows = [uniq[k] for k in sorted(uniq.keys())]

            # fundamentals 업서트 rows
            for r in rows:
                fund_rows.append((
                    t, r["fiscal_date"], r["freq"],
                    r["revenue"], r["op_income"], r["net_income"],
                    r["total_assets"], r["total_liab"], r["equity"],
                    r["ebitda"], r["cash_from_ops"], r["capex"]
                ))

            # metrics 계산 (동일 freq 내에서 이전 값과 비교)
            by_freq = {"A": [], "Q": []}
            for r in rows:
                by_freq[r["freq"]].append(r)
            for freq, lst in by_freq.items():
                prev = None
                for r in lst:
                    m = _calc_metrics(r, prev_row=prev)
                    met_rows.append((
                        t, r["fiscal_date"], r["freq"],
                        m["roe"], m["opm"], m["debt_ratio"], m["roa"], m["rev_growth_yoy"], m["fcf"]
                    ))
                    prev = r

            print(f"✅ {t}: fundamentals {len(rows)} / metrics {len([x for x in met_rows if x[0]==t])}")
        except Exception as e:
            print(f"❌ {t} ERROR: {e}")

    # DB 업서트
    if fund_rows:
        exec_many(UPSERT_FUND, fund_rows)
    if met_rows:
        exec_many(UPSERT_METRICS, met_rows)

    print(f"🎯 완료: fundamentals {len(fund_rows)}행, metrics {len(met_rows)}행 업서트")

if __name__ == "__main__":
    main()
