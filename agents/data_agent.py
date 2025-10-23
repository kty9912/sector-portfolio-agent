import yfinance as yf
import pandas as pd
from langchain_core.tools import tool # <--- @tool 데코레이터 임포트

# (이전과 동일)
SECTOR_ETF_MAP = {
    "반도체": "SOXX", "AI": "BOTZ", "바이오": "XBI", 
    "방위산업": "PPA", "블록체인": "BLOK"
}

# @tool 데코레이터를 붙여 이 함수를 LangChain 'Tool'로 등록합니다.
@tool
def get_sector_etf_momentum(sector_name: str) -> dict:
    """
    Agent 2 (데이터 분석가)의 LangChain Tool
    yfinance를 사용해 섹터 ETF의 기본 모멘텀(예: 50일 이평선)을 계산합니다.
    """
    print(f"[Agent 2] 데이터 분석가 Tool: '{sector_name}' 섹터 모멘텀 분석 시작...")
    
    ticker = SECTOR_ETF_MAP.get(sector_name)
    if not ticker:
        return {"error": "Sector ETF not found"}

    try:
        data = yf.download(ticker, period="3mo", progress=False)
        if data.empty:
            return {"error": f"No data found for {ticker}"}
            
        data['SMA_50'] = data['Close'].rolling(window=50).mean()
        latest_close = data['Close'].iloc[-1]
        latest_sma = data['SMA_50'].iloc[-1]
        momentum_signal = "Positive" if latest_close > latest_sma else "Negative"

        print(f"[Agent 2] 분석 완료. 신호: {momentum_signal}")
        
        return {
            "ticker": ticker,
            "latest_close": round(latest_close, 2),
            "sma_50": round(latest_sma, 2),
            "momentum_signal": momentum_signal
        }
    except Exception as e:
        return {"error": str(e)}

# (news_agent.py의 analyze_sector_sentiment도
#  @tool 데코레이터를 붙여 Tool로 만들 수 있습니다.)

