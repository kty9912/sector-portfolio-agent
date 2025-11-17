"""
experiments/stock_endpoint.py

단일 종목 분석 API 엔드포인트
포트폴리오 시스템 구조를 참고한 구현
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Literal
import json
import os
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

from agent_test.stock_agent_anthropic import run_stock_analysis_agent
from agent_test.stock_agent_langgraph import run_langgraph_stock_analysis
from core.llm_clients import AVAILABLE_MODELS

app = FastAPI(title="AI 단일 종목 분석 시스템")

# 정적 파일 서빙
app.mount("/static", StaticFiles(directory="templates"), name="static")

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

# =====================================================
# Request Model
# =====================================================

class StockAnalysisRequest(BaseModel):
    ticker: str = Field(..., description="종목 코드 (예: 005930.KS)")
    profile: Literal["aggressive", "balanced", "conservative"] = Field(
        default="balanced",
        description="투자 성향"
    )
    model_name: str = Field(
        default="gpt-4o",
        description="분석 모델"
    )


# =====================================================
# API Endpoints
# =====================================================

@app.get("/", response_class=FileResponse)
async def index():
    """메인 페이지"""
    return FileResponse("templates/stock.html")


@app.get("/api/models")
async def get_available_models():
    """사용 가능한 AI 모델 리스트"""
    return {
        "models": AVAILABLE_MODELS,
        "default_model": AVAILABLE_MODELS[0] if AVAILABLE_MODELS else "gpt-4o"
    }


@app.get("/api/stocks")
async def get_available_stocks():
    """분석 가능한 종목 리스트"""
    try:
        from core.db import fetch_all
        
        # DB에서 전체 종목 조회
        sql = """
            SELECT ticker, name_kr, market, industry 
            FROM companies 
            ORDER BY market, ticker
        """
        rows = fetch_all(sql)
        
        stocks = []
        for row in rows:
            stocks.append({
                "ticker": row[0],
                "name": row[1],
                "market": row[2],
                "industry": row[3]
            })
        
        return {
            "stocks": stocks,
            "total": len(stocks)
        }
    
    except Exception as e:
        print(f"❌ 종목 리스트 조회 실패: {e}")
        # Fallback: 기본 종목 리스트
        return {
            "stocks": [
                {"ticker": "005930.KS", "name": "삼성전자", "market": "KOSPI", "industry": "반도체"},
                {"ticker": "000660.KS", "name": "SK하이닉스", "market": "KOSPI", "industry": "반도체"},
                {"ticker": "035420.KS", "name": "NAVER", "market": "KOSPI", "industry": "인터넷"},
                {"ticker": "035720.KS", "name": "카카오", "market": "KOSPI", "industry": "인터넷"},
                {"ticker": "051910.KS", "name": "LG화학", "market": "KOSPI", "industry": "화학"},
                {"ticker": "006400.KS", "name": "삼성SDI", "market": "KOSPI", "industry": "배터리"},
                {"ticker": "373220.KS", "name": "LG에너지솔루션", "market": "KOSPI", "industry": "배터리"},
                {"ticker": "207940.KS", "name": "삼성바이오로직스", "market": "KOSPI", "industry": "바이오"},
                {"ticker": "068270.KS", "name": "셀트리온", "market": "KOSPI", "industry": "바이오"},
                {"ticker": "005380.KS", "name": "현대차", "market": "KOSPI", "industry": "자동차"}
            ],
            "total": 10,
            "fallback": True
        }


@app.post("/api/analyze")
async def analyze_stock(request: StockAnalysisRequest):
    """종목 분석 실행"""
    try:
        print(f"\n{'='*60}")
        print(f"🔍 종목 분석 요청")
        print(f"  티커: {request.ticker}")
        print(f"  성향: {request.profile}")
        print(f"  모델: {request.model_name}")
        print(f"{'='*60}\n")
        
        result = run_stock_analysis_agent(
            ticker=request.ticker,
            profile=request.profile,
            model_name=request.model_name
        )
        
        return JSONResponse(content=result)
    
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stock/anthropic")
async def analyze_stock_anthropic(request: StockAnalysisRequest):
    """Anthropic 기반 종목 분석"""
    try:
        result = run_stock_analysis_agent(
            ticker=request.ticker,
            profile=request.profile,
            model_name=request.model_name
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stock/langgraph")
async def analyze_stock_langgraph(request: StockAnalysisRequest):
    """LangGraph 기반 종목 분석"""
    try:
        result = run_langgraph_stock_analysis(
            ticker=request.ticker,
            profile=request.profile,
            model_name=request.model_name
        )
        return JSONResponse(content=result)
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/quick-info/{ticker}")
async def get_quick_info(ticker: str):
    """종목 간단 정보 조회"""
    try:
        from core.db import fetch_one
        import yfinance as yf
        
        # DB 조회
        sql = "SELECT ticker, name_kr, market, industry FROM companies WHERE ticker = %s"
        row = fetch_one(sql, (ticker,))
        
        if row:
            name_kr = row[1]
            market = row[2]
            industry = row[3]
        else:
            # yfinance fallback
            stock = yf.Ticker(ticker)
            info = stock.info
            name_kr = info.get('longName', ticker)
            market = "KOSPI" if ".KS" in ticker else "KOSDAQ"
            industry = info.get('industry', 'Unknown')
        
        # 현재가
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        current_price = float(hist['Close'].iloc[-1]) if not hist.empty else 0
        
        return {
            "ticker": ticker,
            "name_kr": name_kr,
            "market": market,
            "industry": industry,
            "current_price": current_price
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chart-data/{ticker}")
async def get_chart_data(ticker: str):
    """차트용 데이터 조회 (주가 6개월 + 재무 4분기)"""
    try:
        print(f"\n{'='*60}")
        print(f"📊 차트 데이터 조회 요청: {ticker}")
        print(f"{'='*60}\n")
        
        from core.db import fetch_all
        from datetime import datetime, timedelta
        
        # 1. 주가 데이터 (6개월)
        six_months_ago = (datetime.now() - timedelta(days=180)).date()
        print(f"📅 조회 시작일: {six_months_ago}")
        
        price_sql = """
            SELECT date, close, volume
            FROM prices_daily
            WHERE ticker = %s AND date >= %s
            ORDER BY date
        """
        
        print(f"🔍 주가 데이터 조회 중...")
        price_rows = fetch_all(price_sql, (ticker, six_months_ago))
        print(f"✅ 주가 데이터 {len(price_rows)}개 조회됨")
        
        prices = []
        for row in price_rows:
            prices.append({
                "date": row[0].isoformat(),
                "close": float(row[1]) if row[1] else None,
                "volume": int(row[2]) if row[2] else None
            })
        
        # 2. 재무 데이터 (최근 4분기)
        financial_sql = """
            SELECT f.fiscal_date, f.revenue, f.op_income, f.net_income, 
                   f.total_liab, f.equity,
                   m.roe, m.debt_ratio
            FROM fundamentals f
            LEFT JOIN fin_metrics m ON f.ticker = m.ticker AND f.fiscal_date = m.fiscal_date AND f.freq = m.freq
            WHERE f.ticker = %s AND f.freq = 'Q'
            ORDER BY f.fiscal_date DESC
            LIMIT 4
        """
        
        print(f"🔍 재무 데이터 조회 중...")
        financial_rows = fetch_all(financial_sql, (ticker,))
        print(f"✅ 재무 데이터 {len(financial_rows)}개 조회됨")
        
        financials = []
        for row in financial_rows:
            # fiscal_date로부터 연도와 분기 추출 (예: 2024-03-31 -> 2024Q1)
            fiscal_date = row[0]
            if fiscal_date:
                year = fiscal_date.year
                month = fiscal_date.month
                quarter = (month - 1) // 3 + 1
                period = f"{year}Q{quarter}"
            else:
                period = "N/A"
            
            financials.append({
                "period": period,
                "revenue": float(row[1]) if row[1] else None,
                "operating_income": float(row[2]) if row[2] else None,
                "net_income": float(row[3]) if row[3] else None,
                "total_liab": float(row[4]) if row[4] else None,
                "equity": float(row[5]) if row[5] else None,
                "roe": float(row[6]) if row[6] else None,
                "debt_ratio": float(row[7]) if row[7] else None
            })
        
        # 최신순으로 정렬되어 있으므로 역순으로 변경 (시간순)
        financials.reverse()
        
        result = {
            "ticker": ticker,
            "prices": prices,
            "financials": financials
        }
        
        print(f"📦 반환 데이터: prices={len(prices)}개, financials={len(financials)}개\n")
        
        return result
    
    except Exception as e:
        print(f"❌ 차트 데이터 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sector-comparison/{ticker}")
async def get_sector_comparison(ticker: str):
    """섹터 내 밸류에이션 비교 데이터 조회"""
    try:
        print(f"\n{'='*60}")
        print(f"🔍 섹터 비교 데이터 조회: {ticker}")
        print(f"{'='*60}\n")
        
        from core.db import fetch_all, fetch_one
        
        # 1. 해당 종목의 섹터 확인
        sector_sql = """
            SELECT industry
            FROM companies
            WHERE ticker = %s
        """
        sector_row = fetch_one(sector_sql, (ticker,))
        
        if not sector_row:
            return {"error": "종목을 찾을 수 없습니다"}
        
        sector = sector_row[0]
        print(f"📊 섹터: {sector}")
        
        # 2. 같은 섹터의 다른 종목들 조회 (최대 5개)
        comparison_sql = """
            SELECT 
                c.ticker,
                c.name_kr,
                p.close as current_price,
                f.revenue,
                f.net_income,
                f.equity,
                f.ebitda,
                f.total_assets,
                m.roe
            FROM companies c
            LEFT JOIN (
                SELECT ticker, close
                FROM prices_daily
                WHERE (ticker, date) IN (
                    SELECT ticker, MAX(date)
                    FROM prices_daily
                    GROUP BY ticker
                )
            ) p ON c.ticker = p.ticker
            LEFT JOIN (
                SELECT ticker, revenue, net_income, equity, ebitda, total_assets
                FROM fundamentals
                WHERE (ticker, fiscal_date) IN (
                    SELECT ticker, MAX(fiscal_date)
                    FROM fundamentals
                    WHERE freq = 'Q'
                    GROUP BY ticker
                )
            ) f ON c.ticker = f.ticker
            LEFT JOIN (
                SELECT ticker, roe
                FROM fin_metrics
                WHERE (ticker, fiscal_date) IN (
                    SELECT ticker, MAX(fiscal_date)
                    FROM fin_metrics
                    WHERE freq = 'Q'
                    GROUP BY ticker
                )
            ) m ON c.ticker = m.ticker
            WHERE c.industry = %s
            ORDER BY f.revenue DESC NULLS LAST
            LIMIT 5
        """
        
        rows = fetch_all(comparison_sql, (sector,))
        print(f"✅ {len(rows)}개 종목 조회됨")
        
        comparisons = []
        for row in rows:
            # PER 계산: 주가 / EPS, EPS = net_income / shares (간단 추정)
            per = None
            pbr = None
            market_cap = None
            ev_ebitda = None
            
            current_price = float(row[2]) if row[2] else None
            revenue = float(row[3]) if row[3] else None
            net_income = float(row[4]) if row[4] else None
            equity = float(row[5]) if row[5] else None
            ebitda = float(row[6]) if row[6] else None
            total_assets = float(row[7]) if row[7] else None
            
            # 시가총액 추정 (equity * 2 정도로 간단 추정)
            if equity and equity > 0:
                market_cap = equity * 2.5
            
            # PBR 계산: 시가총액 / 자기자본
            if market_cap and equity and equity > 0:
                pbr = market_cap / equity
            
            # PER 계산: 시가총액 / 순이익
            if market_cap and net_income and net_income > 0:
                per = market_cap / net_income
            
            # EV/EBITDA 계산: 시가총액 / EBITDA (부채 고려 안함)
            if market_cap and ebitda and ebitda > 0:
                ev_ebitda = market_cap / ebitda
            
            comparisons.append({
                "ticker": row[0],
                "name": row[1],
                "current_price": current_price,
                "per": per,
                "pbr": pbr,
                "ev_ebitda": ev_ebitda,
                "market_cap": market_cap,
                "is_target": row[0] == ticker
            })
        
        result = {
            "ticker": ticker,
            "sector": sector,
            "comparisons": comparisons
        }
        
        print(f"📦 섹터 비교 데이터 반환: {len(comparisons)}개 종목\n")
        
        return result
    
    except Exception as e:
        print(f"❌ 섹터 비교 데이터 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# PDF 다운로드 엔드포인트
# =====================================================

@app.post("/api/stock/download-pdf")
async def download_pdf(request: dict):
    """Playwright를 사용한 PDF 다운로드"""
    try:
        html_content = request.get("html")
        if not html_content:
            raise HTTPException(status_code=400, detail="HTML 데이터가 없습니다")
        
        # 한글 폰트 및 PDF용 CSS 추가
        font_css = """
        <style>
            @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
            * {
                font-family: 'Malgun Gothic', '맑은 고딕', Pretendard, sans-serif !important;
            }
            /* PDF용 폰트 크기 최적화 - 디자인은 유지 */
            @media print {
                /* 배경 제거 */
                body {
                    background: white !important;
                    padding: 20px !important;
                }
                .container {
                    background: white !important;
                    box-shadow: none !important;
                }
                .panel {
                    box-shadow: none !important;
                }
                
                /* 버튼 숨김 */
                .btn-primary { display: none !important; }
                #downloadPdfBtn { display: none !important; }
                details { display: none !important; }
                
                /* 이미지로 변환된 차트는 그대로 표시 */
                img {
                    page-break-inside: avoid;
                    max-width: 100% !important;
                    height: auto !important;
                }
                
                /* 섹션 - 페이지 분할 방지 */
                .section {
                    page-break-inside: avoid;
                }
                
                /* 그림자 제거 */
                .metric-card {
                    box-shadow: none !important;
                }
                .summary-box {
                    box-shadow: none !important;
                }
                .disclaimer {
                    box-shadow: none !important;
                }
                
                /* 헤더 섹션 폰트 크기 조정 */
                .stock-header > div:first-child {
                    font-size: 1.2em !important;  /* 제목 크기 축소 */
                }
                .stock-header > div:nth-child(2) {
                    font-size: 0.85em !important;
                }
                .stock-header > div:nth-child(3) {
                    font-size: 0.8em !important;
                }
                
                /* 폰트 크기만 줄임 (디자인은 유지) */
                .section-title {
                    font-size: 1.1em !important;  /* 섹션 제목 축소 */
                }
                .metric-label {
                    font-size: 0.75em !important;
                }
                .metric-value {
                    font-size: 1.2em !important;
                }
                .metric-unit {
                    font-size: 0.85em !important;
                }
                .summary-box {
                    font-size: 0.85em !important;
                    line-height: 1.5 !important;
                }
                .summary-box h3, .summary-box h4 {
                    font-size: 1.1em !important;
                }
                .summary-box p {
                    font-size: 0.85em !important;
                }
                
                /* 시나리오 비교 테이블 */
                table {
                    font-size: 0.8em !important;
                }
                table th {
                    font-size: 0.85em !important;
                }
                table td {
                    font-size: 0.8em !important;
                }
                
                /* 면책 조항 */
                .disclaimer {
                    page-break-inside: avoid !important;
                }
                .disclaimer p {
                    font-size: 0.75em !important;
                    line-height: 1.5 !important;
                }
                .disclaimer strong {
                    font-size: 0.85em !important;
                }
            }
        </style>
        """
        
        html_with_font = html_content.replace('<head>', '<head>' + font_css)
        
        # Playwright로 PDF 생성
        def generate_pdf():
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_with_font)
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(2000)
                
                pdf_bytes = page.pdf(
                    format='A4',
                    landscape=False,
                    margin={
                        'top': '15mm',
                        'right': '15mm',
                        'bottom': '15mm',
                        'left': '15mm'
                    },
                    print_background=True,
                    prefer_css_page_size=True
                )
                
                browser.close()
                return pdf_bytes
        
        # 동기 함수를 별도 스레드에서 실행
        import asyncio
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            pdf_bytes = await asyncio.get_event_loop().run_in_executor(executor, generate_pdf)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stock_analysis_{timestamp}.pdf"
        
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        print(f"❌ PDF 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")


# =====================================================
# 실행
# =====================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*60)
    print("🚀 AI 단일 종목 분석 시스템 시작")
    print("="*60)
    print("📍 http://localhost:8001 에서 확인하세요")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
