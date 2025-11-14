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
from core.llm_clients import AVAILABLE_MODELS

app = FastAPI(title="AI 단일 종목 분석 시스템")

# 정적 파일 서빙
app.mount("/static", StaticFiles(directory="experiments/templates/stock"), name="static")


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
    return FileResponse("experiments/templates/stock/stock_analysis.html")


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
                    font-size: 1.5em !important;
                }
                .stock-header > div:nth-child(2) {
                    font-size: 0.9em !important;
                }
                .stock-header > div:nth-child(3) {
                    font-size: 0.85em !important;
                }
                
                /* 폰트 크기만 줄임 (디자인은 유지) */
                .section-title {
                    font-size: 1.3em !important;
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
