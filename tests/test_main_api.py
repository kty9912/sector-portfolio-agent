import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# GET 엔드포인트 테스트
def test_get_sectors(monkeypatch):
    import agents.portfolio_agent_anthropic as pa
    pa.fetch_dicts = lambda sql, params=None: [{"industry": "반도체"}]
    response = client.get("/api/sectors")
    assert response.status_code == 200
    assert "sectors" in response.json()
    from agents.portfolio_agent_anthropic import get_sectors
    assert response.json()["sectors"] == get_sectors()


def test_get_stocks(monkeypatch):
    import agents.portfolio_agent_anthropic as pa
    pa.fetch_dicts = lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}]
    response = client.get("/api/stocks")
    assert response.status_code == 200
    assert "stocks" in response.json()


def test_get_models(monkeypatch):
    monkeypatch.setattr("main.app.dependency_overrides", {}, raising=False)
    response = client.get("/api/models")
    assert response.status_code == 200
    assert "models" in response.json()

# 종목 정보 조회 테스트 (존재하지 않는 티커도 에러 없이 반환)
def test_get_quick_info(monkeypatch):
    import core.db
    monkeypatch.setattr(core.db, "fetch_one", lambda sql, params=None: ("005930.KS", "삼성전자", "KOSPI", "반도체"))
    import yfinance
    import pandas as pd
    class DummyTicker:
        info = {"longName": "삼성전자", "industry": "반도체"}
        def history(self, period):
            class DummyHist:
                empty = False
                def __getitem__(self, key):
                    if key == "Close":
                        s = pd.Series([80000])
                        s.iloc[-1] = 80000
                        return s
                    raise KeyError(key)
            return DummyHist()
    monkeypatch.setattr(yfinance, "Ticker", lambda ticker: DummyTicker())
    response = client.get("/api/quick-info/005930.KS")
    assert response.status_code == 200
    data = response.json()
    assert "ticker" in data
    assert "name_kr" in data

# POST 엔드포인트 테스트 (Smoke)
import agents.portfolio_agent_anthropic
def test_analyze_anthropic(monkeypatch):
    # Agent 함수 모킹
    import agents.portfolio_agent_anthropic as pa
    pa.run_portfolio_agent = lambda **kwargs: {"success": True, "final_report": "{\"ai_summary\": \"테스트\"}"}
    # DB 함수 모킹
    pa.fetch_dicts = lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자", "industry": "반도체"}]
    pa.get_chat_model = lambda model_name: type("DummyLLM", (), {
        "invoke": lambda self, *args, **kwargs: type("DummyResponse", (), {"content": "{\"ai_summary\": \"테스트\"}"})(),
        "bind_tools": lambda self, *args, **kwargs: self
    })()
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
    import agents.stock_agent_anthropic as sa
    sa.run_stock_analysis_agent = lambda **kwargs: {
        "basic_info": {
            "ticker": "005930.KS",
            "name_kr": "삼성전자",
            "market": "KOSPI",
            "industry": "반도체",
            "market_cap_level": "대형주",
            "summary_sentence": "삼성전자 요약"
        },
        "ai_summary": "테스트"
    }
    import main
    monkeypatch.setattr(main, "run_stock_analysis_agent", sa.run_stock_analysis_agent)
    import agents.portfolio_agent_anthropic as pa
    pa.get_chat_model = lambda model_name: type("DummyLLM", (), {
        "invoke": lambda self, *args, **kwargs: type("DummyResponse", (), {"content": "{\"ai_summary\": \"테스트\"}"})(),
        "bind_tools": lambda self, *args, **kwargs: self
    })()
    import agents.stock_agent_anthropic as sa
    monkeypatch.setattr(sa, "fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자", "industry": "반도체"}])
    monkeypatch.setattr(sa, "fetch_one", lambda sql, params=None: ("005930.KS", "삼성전자", "KOSPI", "반도체"))
    monkeypatch.setattr(sa, "get_chat_model", lambda model_name: type("DummyLLM", (), {
        "invoke": lambda self, *args, **kwargs: type("DummyResponse", (), {"content": "{\"ai_summary\": \"테스트\"}"})(),
        "bind_tools": lambda self, *args, **kwargs: self
    })())
    monkeypatch.setattr(sa, "run_stock_analysis_agent", lambda *args, **kwargs: {
        "basic_info": {
            "ticker": "005930.KS",
            "name_kr": "삼성전자",
            "market": "KOSPI",
            "industry": "반도체",
            "market_cap_level": "대형주",
            "summary_sentence": "삼성전자 요약"
        },
        "ai_summary": "테스트"
    })
    payload = {"ticker": "005930.KS", "profile": "balanced", "model_name": "gpt-4o"}
    response = client.post("/api/stock/anthropic", json=payload)
    assert response.status_code == 200
    assert "basic_info" in response.json()


import agents.stock_agent_langgraph
def test_analyze_stock_langgraph(monkeypatch):
    import agents.stock_agent_langgraph as sl
    sl.run_langgraph_stock_analysis = lambda **kwargs: {
        "basic_info": {
            "ticker": "005930.KS",
            "name_kr": "삼성전자",
            "market": "KOSPI",
            "industry": "반도체",
            "market_cap_level": "대형주",
            "summary_sentence": "삼성전자 요약"
        },
        "ai_summary": "테스트"
    }
    import main
    monkeypatch.setattr(main, "run_langgraph_stock_analysis", sl.run_langgraph_stock_analysis)
    import agents.portfolio_agent_anthropic as pa
    pa.get_chat_model = lambda model_name: type("DummyLLM", (), {
        "invoke": lambda self, *args, **kwargs: type("DummyResponse", (), {"content": "{\"ai_summary\": \"테스트\"}"})(),
        "bind_tools": lambda self, *args, **kwargs: self
    })()
    import agents.stock_agent_langgraph as sl
    monkeypatch.setattr(sl, "fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자", "industry": "반도체"}])
    monkeypatch.setattr(sl, "fetch_one", lambda sql, params=None: ("005930.KS", "삼성전자", "KOSPI", "반도체"))
    monkeypatch.setattr(sl, "get_chat_model", lambda model_name: type("DummyLLM", (), {
        "invoke": lambda self, *args, **kwargs: type("DummyResponse", (), {"content": "{\"ai_summary\": \"테스트\"}"})(),
        "bind_tools": lambda self, *args, **kwargs: self
    })())
    monkeypatch.setattr(sl, "run_langgraph_stock_analysis", lambda *args, **kwargs: {
        "basic_info": {
            "ticker": "005930.KS",
            "name_kr": "삼성전자",
            "market": "KOSPI",
            "industry": "반도체",
            "market_cap_level": "대형주",
            "summary_sentence": "삼성전자 요약"
        },
        "ai_summary": "테스트"
    })
    payload = {"ticker": "005930.KS", "profile": "balanced", "model_name": "gpt-4o"}
    response = client.post("/api/stock/langgraph", json=payload)
    assert response.status_code == 200
    assert "basic_info" in response.json()
