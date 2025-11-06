import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

# 에이전트 모듈 임포트
from agents.data_agent import get_sector_etf_momentum
from agents.news_agent import analyze_sector_sentiment

app = FastAPI(
    title="Sector Portfolio Agent API",
    description="AI-powered sector portfolio generator"
)

# Agent 1 (금융 코디네이터)의 역할을 이 엔드포인트가 수행합니다.
@app.post("/generate-portfolio-mvp")
async def generate_portfolio_mvp(sector_name: str):
    """
    MVP 파이프라인:
    1. 데이터 분석가(Agent 2)가 모멘텀을 분석합니다.
    2. 뉴스 분석가(Agent 5)가 감성을 분석합니다.
    3. 결과를 취합하여 반환합니다.
    """
    print(f"[Agent 1] 코디네이터: '{sector_name}' 분석 작업 시작...")
    
    # 1. 데이터 분석가 호출
    momentum_result = get_sector_etf_momentum(sector_name)
    
    # 2. 뉴스 분석가 호출
    sentiment_result = analyze_sector_sentiment(sector_name)
    
    print("[Agent 1] 코디네이터: 모든 분석 완료. 결과 취합 중...")

    # 3. 결과 취합 (Agent 7: 보고서 생성기의 초기 버전)
    final_report = {
        "sector": sector_name,
        "momentum_analysis": momentum_result,
        "sentiment_analysis": sentiment_result,
        "combined_assessment": "Analysis complete. Awaiting portfolio model." 
    }
    
    return final_report

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

