import pytest
from agents.portfolio_agent_multi import run_multi_agent_portfolio

@pytest.mark.skip(reason="DB, LLM 등 외부 환경 의존")
def test_run_multi_agent_portfolio_smoke():
    result = run_multi_agent_portfolio(
        budget=1000000,
        investment_targets={"sectors": ["반도체"], "tickers": []},
        risk_profile="중립",
        investment_period="단기",
        additional_prompt="테스트"
    )
    assert isinstance(result, dict)
    assert "success" in result
