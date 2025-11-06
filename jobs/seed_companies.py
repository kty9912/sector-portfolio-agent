from core.db import exec_sql

DDL = """
CREATE TABLE IF NOT EXISTS companies (
  ticker     TEXT PRIMARY KEY,
  krx_code   TEXT NOT NULL,
  name_kr    TEXT NOT NULL,
  market     TEXT NOT NULL,
  industry   TEXT,
  is_active  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies;
CREATE TRIGGER trg_companies_updated_at
BEFORE UPDATE ON companies
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
"""

UPSERT = """
INSERT INTO companies (ticker, krx_code, name_kr, market, industry, is_active)
VALUES
('005930.KS','005930','삼성전자','KOSPI',NULL,TRUE),
('000660.KS','000660','SK하이닉스','KOSPI',NULL,TRUE),
('012450.KS','012450','한화에어로스페이스','KOSPI',NULL,TRUE),
('068270.KS','068270','셀트리온','KOSPI',NULL,TRUE),
('042700.KS','042700','한미반도체','KOSPI',NULL,TRUE),
('017670.KS','017670','SK텔레콤','KOSPI',NULL,TRUE),
('034020.KS','034020','두산에너빌리티','KOSPI',NULL,TRUE),
('051600.KS','051600','한전KPS','KOSPI',NULL,TRUE),
('298040.KS','298040','효성중공업','KOSPI',NULL,TRUE),
('010120.KS','010120','LS일렉트릭','KOSPI',NULL,TRUE),
('009540.KS','009540','HD한국조선해양','KOSPI',NULL,TRUE),
('079550.KS','079550','LIG넥스원','KOSPI',NULL,TRUE),
('207940.KS','207940','삼성바이오로직스','KOSPI',NULL,TRUE),
('196170.KQ','196170','알테오젠','KOSDAQ',NULL,TRUE)
ON CONFLICT (ticker) DO UPDATE SET
  krx_code=EXCLUDED.krx_code,
  name_kr=EXCLUDED.name_kr,
  market=EXCLUDED.market,
  industry=COALESCE(EXCLUDED.industry, companies.industry),
  is_active=EXCLUDED.is_active;
"""

if __name__ == "__main__":
    exec_sql(DDL)
    exec_sql(UPSERT)
    print("companies 시드 완료")
