"""
experiments/stock_endpoint.py

단일 종목 분석 API 엔드포인트
포트폴리오 시스템 구조를 참고한 구현
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, Literal
import json
import os
from pathlib import Path

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
