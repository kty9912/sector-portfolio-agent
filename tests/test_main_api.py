import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# GET 엔드포인트 테스트
def test_get_sectors():
    response = client.get("/api/sectors")
    assert response.status_code == 200
    assert "sectors" in response.json()


def test_get_stocks():
    response = client.get("/api/stocks")
    assert response.status_code == 200
    assert "stocks" in response.json()


def test_get_models():
    response = client.get("/api/models")
    assert response.status_code == 200
    assert "models" in response.json()

# 종목 정보 조회 테스트 (존재하지 않는 티커도 에러 없이 반환)
def test_get_quick_info():
    response = client.get("/api/quick-info/005930.KS")
    assert response.status_code == 200
    data = response.json()
    assert "ticker" in data
    assert "name_kr" in data

# POST 엔드포인트 테스트 (Smoke)
import agents.portfolio_agent_anthropic
def test_analyze_anthropic(monkeypatch):
    # Agent 함수 모킹
    monkeypatch.setattr(agents.portfolio_agent_anthropic, "run_portfolio_agent", lambda **kwargs: {"success": True, "final_report": "{\"ai_summary\": \"테스트\"}"})
    payload = {
        "budget": 1000000,
        "investment_targets": {"sectors": ["반도체"], "tickers": ["005930.KS"]},
        "risk_profile": "중립",
        "investment_period": "단기",
        "model_name": "gpt-4o",  # 실제 지원되는 모델명으로 변경
        "additional_prompt": "테스트"
    }
    response = client.post("/api/analyze/anthropic", json=payload)
    assert response.status_code == 200
    assert response.json()["success"]

# PDF 다운로드 API는 실제 파일 생성이 필요하므로, 여기서는 생략 또는 별도 환경에서 테스트

# 종목 분석 API 테스트 (Smoke)
import agents.stock_agent_anthropic
def test_analyze_stock_anthropic(monkeypatch):
    # 실제 반환 구조에 맞게 모킹
    monkeypatch.setattr(agents.stock_agent_anthropic, "run_stock_analysis_agent", lambda **kwargs: {"basic_info": {"name_kr": "삼성전자"}, "ai_summary": "테스트"})
    payload = {"ticker": "005930.KS", "profile": "balanced", "model_name": "gpt-4o"}
    response = client.post("/api/stock/anthropic", json=payload)
    assert response.status_code == 200
    assert "basic_info" in response.json()


import agents.stock_agent_langgraph
def test_analyze_stock_langgraph(monkeypatch):
    monkeypatch.setattr(agents.stock_agent_langgraph, "run_langgraph_stock_analysis", lambda **kwargs: {"basic_info": {"name_kr": "삼성전자"}, "ai_summary": "테스트"})
    payload = {"ticker": "005930.KS", "profile": "balanced", "model_name": "gpt-4o"}
    response = client.post("/api/stock/langgraph", json=payload)
    assert response.status_code == 200
    assert "basic_info" in response.json()
