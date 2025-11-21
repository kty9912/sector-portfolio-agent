import pytest
from agents.portfolio_agent_multi import (
    load_available_stocks, load_sector_map, get_available_stocks, get_sector_map,
    get_stock_prices, get_financial_metrics, get_technical_signals, get_company_info,
    parse_llm_json, run_multi_agent_portfolio
)

# 1. DB/데이터 로드 함수 테스트
def test_load_available_stocks(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_multi.fetch_dicts", lambda sql: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = get_available_stocks()
    assert isinstance(stocks, list)
    assert len(stocks) > 0

def test_load_sector_map(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_multi.fetch_dicts", lambda sql: [{"ticker": "005930.KS", "industry": "반도체"}])
    sector_map = get_sector_map()
    assert isinstance(sector_map, dict)
    assert len(sector_map) > 0

# 2. 주요 Tool 함수 테스트 (조회만)
def test_get_stock_prices(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_multi.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_multi.get_stock_prices", lambda ticker: {"ticker": ticker, "current_price": 70000})
    result = get_stock_prices.invoke(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

def test_get_financial_metrics(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_multi.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_multi.get_financial_metrics", lambda ticker: {"ticker": ticker, "roe": 10})
    result = get_financial_metrics.invoke(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

def test_get_technical_signals(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_multi.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_multi.get_technical_signals", lambda ticker: {"ticker": ticker, "rsi": 50})
    result = get_technical_signals.invoke(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

def test_get_company_info(monkeypatch):
    monkeypatch.setattr("agents.portfolio_agent_multi.fetch_dicts", lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자"}])
    stocks = load_available_stocks()
    ticker = stocks[0][0]
    monkeypatch.setattr("agents.portfolio_agent_multi.get_company_info", lambda ticker: {"ticker": ticker, "name_kr": "삼성전자"})
    result = get_company_info.invoke(ticker)
    assert isinstance(result, dict)
    assert "ticker" in result

# 3. JSON 파싱 함수 테스트
def test_parse_llm_json_valid():
    raw = '{"ai_summary": "요약", "portfolio_allocation": []}'
    result = parse_llm_json(raw)
    assert isinstance(result, dict)
    assert "ai_summary" in result

def test_parse_llm_json_codeblock():
    raw = """```json\n{\"ai_summary\": \"요약\", \"portfolio_allocation\": []}\n```"""
    result = parse_llm_json(raw)
    assert isinstance(result, dict)
    assert "ai_summary" in result

def test_parse_llm_json_invalid():
    with pytest.raises(ValueError):
        parse_llm_json("")

# 4. 실행 함수 smoke test (LLM mock)
def test_run_multi_agent_portfolio_smoke(monkeypatch):
    from agents import portfolio_agent_multi
    def mock_get_chat_model(model_name):
        class DummyLLM:
            def invoke(self, *args, **kwargs):
                class DummyResponse:
                    content = '{"ai_summary": "요약", "portfolio_allocation": []}'
                return DummyResponse()
        return DummyLLM()
    monkeypatch.setattr(portfolio_agent_multi, "get_chat_model", mock_get_chat_model)
    import agents.portfolio_agent_multi as pm
    pm.fetch_dicts = lambda sql, params=None: [{"ticker": "005930.KS", "name_kr": "삼성전자", "industry": "반도체"}]
    result = run_multi_agent_portfolio(
        budget=1000000,
        investment_targets={"sectors": ["반도체"], "tickers": []},
        risk_profile="중립",
        investment_period="단기",
        additional_prompt="테스트"
    )
    assert isinstance(result, dict)
    assert "ai_summary" in result
    assert "portfolio_allocation" in result
