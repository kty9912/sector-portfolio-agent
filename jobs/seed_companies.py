from core.db import exec_sql

# 산업 코드 매핑
INDUSTRY_CODE_MAP = {
    "SEMI": "반도체",
    "BIO": "바이오",
    "DEF": "방산",
    "AI": "AI",
    "NUC": "원자력",
    "UTILSVC": "전력망",
    "SHP": "조선",
}

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
('035420.KS','035420','NAVER','KOSPI','AI',TRUE),
('035720.KS','035720','카카오','KOSPI','AI',TRUE),
('259960.KS','259960','크래프톤','KOSPI','AI',TRUE),
('005930.KS','005930','삼성전자','KOSPI','SEMI',TRUE),
('000660.KS','000660','SK하이닉스','KOSPI','SEMI',TRUE),
('042700.KS','042700','한미반도체','KOSPI','SEMI',TRUE),
('010120.KS','010120','LS ELECTRIC','KOSPI','UTILSVC',TRUE),
('298040.KS','298040','효성중공업','KOSPI','UTILSVC',TRUE),
('267260.KS','267260','HD현대일렉트릭','KOSPI','UTILSVC',TRUE),
('015760.KS','015760','한국전력','KOSPI','NUC',TRUE),
('034020.KS','034020','두산에너빌리티','KOSPI','NUC',TRUE),
('051600.KS','051600','한전KPS','KOSPI','NUC',TRUE),
('009540.KS','009540','HD한국조선해양','KOSPI','SHP',TRUE),
('010140.KS','010140','삼성중공업','KOSPI','SHP',TRUE),
('042660.KS','042660','한화오션','KOSPI','SHP',TRUE),
('012450.KS','012450','한화에어로스페이스','KOSPI','DEF',TRUE),
('079550.KS','079550','LIG넥스원','KOSPI','DEF',TRUE),
('272210.KS','272210','한화시스템','KOSPI','DEF',TRUE),
('207940.KS','207940','삼성바이오로직스','KOSPI','BIO',TRUE),
('068270.KS','068270','셀트리온','KOSPI','BIO',TRUE),
('326030.KS','326030','SK바이오팜','KOSPI','BIO',TRUE)
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