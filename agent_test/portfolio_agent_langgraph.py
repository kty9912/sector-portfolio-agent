"""
portfolio_agent_langgraph.py

LangGraph 기반 투자 포트폴리오 분석 Agent (v2)
Anthropic Tool Use 방식의 순차적 워크플로우
"""

from typing import Any, Dict, List, Optional, TypedDict
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from core.db import fetch_dicts
from core.llm_clients import get_chat_model
from jobs.seed_companies import INDUSTRY_CODE_MAP

# =====================================================
# State Definition
# =====================================================

class AgentState(TypedDict):
    """Agent의 상태"""
    budget: int
    investment_targets: Dict[str, List[str]]
    risk_profile: str
    investment_period: str
    additional_prompt: str
    
    # 수집된 데이터
    company_infos: Dict[str, Dict[str, Any]]  # ticker -> company info
    stock_prices: Dict[str, Dict[str, Any]]   # ticker -> price data
    financial_metrics: Dict[str, Dict[str, Any]]  # ticker -> financial data
    technical_signals: Dict[str, Dict[str, Any]]  # ticker -> signals
    correlation_data: Dict[str, Any]
    
    # 분석 결과
    portfolio_allocation: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]
    chart_data: Dict[str, Any]
    ai_summary: str
    
    # 메시지 히스토리
    messages: List[BaseMessage]
    iteration: int


# =====================================================
# DB 로드 함수
# =====================================================

def load_available_stocks() -> List[tuple]:
    """DB에서 활성 종목 로드"""
    companies = fetch_dicts("SELECT ticker, name_kr FROM companies WHERE is_active = TRUE ORDER BY ticker")
    return [(c.get("ticker"), c.get("name_kr")) for c in companies]

def load_sector_map() -> Dict[str, str]:
    """DB에서 섹터 맵 로드"""
    companies = fetch_dicts("SELECT ticker, industry FROM companies WHERE is_active = TRUE")
    sector_map = {}
    for c in companies:
        ticker = c.get("ticker")
        industry_code = c.get("industry")
        sector_kr = INDUSTRY_CODE_MAP.get(industry_code, industry_code)
        sector_map[ticker] = sector_kr
    return sector_map

def load_sectors() -> List[str]:
    """DB에서 고유 섹터 로드"""
    companies = fetch_dicts("SELECT DISTINCT industry FROM companies WHERE is_active = TRUE")
    sectors_set = set()
    for c in companies:
        industry_code = c.get("industry")
        if industry_code:
            sector_kr = INDUSTRY_CODE_MAP.get(industry_code)
            if sector_kr:
                sectors_set.add(sector_kr)
    return sorted(list(sectors_set))

AVAILABLE_STOCKS = load_available_stocks()
SECTOR_MAP = load_sector_map()
SECTORS = load_sectors()

INDUSTRY_TRENDS = {
    "AI": "생성형 AI 확산으로 반도체·클라우드 수요 급증. 기업 간 AI 플랫폼 경쟁 심화로 시장 고성장세 유지.",
    "반도체": "AI 반도체 수요 폭발로 고성능 메모리(HBM) 공급 부족 지속. 파운드리와 팹리스 동반 성장세.",
    "전력망": "전력망 현대화 및 전력 인프라 교체 수요 확대. 스마트그리드 및 배전 자동화 관련주 수혜 예상.",
    "원자력": "탄소중립 기조 속 원전 재평가. 중동·동유럽 프로젝트 수주 본격화로 장기 성장 모멘텀 확보.",
    "조선": "친환경·LNG선 중심의 수주 호황 지속. 해운 운임 안정화와 글로벌 교체 수요로 업황 긍정적.",
    "방산": "지정학적 긴장 고조로 국방예산 확대. 유럽·중동 중심의 수출 증가세로 중장기 성장 기대.",
    "바이오": "글로벌 바이오시밀러 시장 확대 지속. 미국 FDA 승인 증가와 신약개발 투자 회복세 뚜렷.",
}


# =====================================================
# Tool 정의 (LangChain @tool 데코레이터)
# =====================================================

def to_float(val) -> float:
    if val is None:
        return 0.0
    return float(val) if isinstance(val, Decimal) else val


@tool
def get_stock_prices(ticker: str, days: int = 250) -> Dict[str, Any]:
    """특정 종목의 최근 주가 데이터를 조회합니다."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    prices = fetch_dicts(
        """SELECT date, close, volume FROM prices_daily
           WHERE ticker = %s AND date >= %s
           ORDER BY date DESC LIMIT %s""",
        (ticker, cutoff_date, days)
    )
    
    if not prices:
        return {"error": f"'{ticker}' 종목의 주가 데이터를 찾을 수 없습니다."}
    
    latest = prices[0]
    oldest = prices[-1] if len(prices) > 1 else latest
    
    period_return = 0
    if to_float(oldest.get("close")) > 0:
        period_return = (to_float(latest.get("close")) - to_float(oldest.get("close"))) / to_float(oldest.get("close"))
    
    closes = [to_float(p.get("close", 0)) for p in prices]
    returns = []
    for i in range(1, min(60, len(closes))):
        if closes[i-1] > 0:
            returns.append((closes[i-1] - closes[i]) / closes[i])
    
    volatility = np.std(returns) * np.sqrt(252) if returns else 0
    
    return {
        "ticker": ticker,
        "current_price": to_float(latest.get("close")),
        "period_return_pct": round(period_return * 100, 2),
        "volatility_annual": round(volatility * 100, 2),
        "avg_volume": int(np.mean([to_float(p.get("volume", 0)) for p in prices]))
    }


@tool
def get_financial_metrics(ticker: str, quarters: int = 4) -> Dict[str, Any]:
    """재무 지표를 조회합니다. ROE, 부채비율, 매출성장률 등."""
    metrics = fetch_dicts(
        """SELECT fiscal_date, roe, opm, debt_ratio, roa, rev_growth_yoy
           FROM fin_metrics WHERE ticker = %s AND freq = 'Q'
           ORDER BY fiscal_date DESC LIMIT %s""",
        (ticker, quarters)
    )
    
    if not metrics:
        return {"error": f"'{ticker}' 종목의 재무 지표를 찾을 수 없습니다."}
    
    latest = metrics[0]
    
    roe = to_float(latest.get("roe", 0)) * 100
    opm = to_float(latest.get("opm", 0)) * 100
    debt_ratio = to_float(latest.get("debt_ratio", 0))
    rev_growth = to_float(latest.get("rev_growth_yoy", 0)) * 100
    
    roe_score = min(roe / 15 * 100, 100) if roe > 0 else 0
    opm_score = min(opm / 10 * 100, 100) if opm > 0 else 0
    debt_score = max(100 - debt_ratio, 0)
    growth_score = min(max(rev_growth / 20 * 100, 0), 100)
    
    financial_score = (roe_score * 0.3 + opm_score * 0.2 + debt_score * 0.3 + growth_score * 0.2)
    
    return {
        "ticker": ticker,
        "roe": round(roe, 2),
        "opm": round(opm, 2),
        "debt_ratio": round(debt_ratio, 2),
        "revenue_growth_yoy": round(rev_growth, 2),
        "financial_score": round(financial_score, 1)
    }


@tool
def get_technical_signals(ticker: str) -> Dict[str, Any]:
    """기술적 지표를 조회합니다. RSI, MA, 모멘텀 등."""
    signals = fetch_dicts(
        "SELECT * FROM signals_latest WHERE ticker = %s",
        (ticker,)
    )
    
    if not signals:
        return {"error": f"'{ticker}' 기술적 지표 데이터 없음"}
    
    sig = signals[0]
    
    rsi = to_float(sig.get("rsi14", 50))
    rsi_score = 100 if 30 <= rsi <= 70 else (50 if 20 <= rsi <= 80 else 20)
    
    momentum = to_float(sig.get("momentum_20d", 0)) * 100
    momentum_score = min(max((momentum + 10) / 0.2, 0), 100)
    
    vol = to_float(sig.get("vol_20d", 0))
    vol_score = max(50 - vol * 10, 0)
    
    data_analysis_score = (rsi_score * 0.4 + momentum_score * 0.4 + vol_score * 0.2)
    
    return {
        "ticker": ticker,
        "rsi14": round(rsi, 2),
        "momentum_20d": round(momentum, 2),
        "vol_20d": round(vol, 4),
        "data_analysis_score": round(data_analysis_score, 1)
    }


@tool
def get_company_info(ticker: str) -> Dict[str, Any]:
    """기업 정보를 조회합니다."""
    companies = fetch_dicts("SELECT ticker, name_kr, industry FROM companies WHERE ticker = %s", (ticker,))
    
    if not companies:
        return {"error": f"'{ticker}' 종목 정보를 찾을 수 없습니다."}
    
    company = companies[0]
    sector_code = company.get("industry")
    sector_kr = INDUSTRY_CODE_MAP.get(sector_code, sector_code)
    
    return {
        "ticker": ticker,
        "name": company.get("name_kr"),
        "sector": sector_kr,
        "industry_trend": INDUSTRY_TRENDS.get(sector_kr, "정보 없음")
    }


@tool
def get_stocks_by_sector(sectors: List[str]) -> Dict[str, Any]:
    """특정 섹터의 종목 리스트를 조회합니다."""
    result = {}
    for sector in sectors:
        stocks = [(ticker, name) for ticker, name in AVAILABLE_STOCKS if SECTOR_MAP.get(ticker) == sector]
        result[sector] = [{"ticker": t, "name": n} for t, n in stocks]
    
    return {"sector_stocks": result}


@tool
def calculate_portfolio_performance(tickers: List[str], weights: List[float]) -> Dict[str, Any]:
    """포트폴리오 예상 성과를 계산합니다."""
    if len(tickers) != len(weights) or abs(sum(weights) - 1.0) > 0.01:
        return {"error": "종목 수와 가중치가 일치하지 않거나 가중치 합이 1이 아닙니다."}
    
    stock_metrics = []
    for ticker in tickers:
        prices = fetch_dicts(
            """SELECT close FROM prices_daily WHERE ticker = %s
               ORDER BY date DESC LIMIT 250""",
            (ticker,)
        )
        if not prices:
            continue
        
        closes = [to_float(p.get("close", 0)) for p in reversed(prices)]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes)) if closes[i-1] > 0]
        
        annual_return = np.mean(returns) * 252 if returns else 0
        annual_vol = np.std(returns) * np.sqrt(252) if returns else 0
        
        stock_metrics.append({
            "returns": returns,
            "annual_return": annual_return,
            "annual_vol": annual_vol
        })
    
    if not stock_metrics:
        return {"error": "종목 데이터 부족"}
    
    portfolio_return = sum(m["annual_return"] * w for m, w in zip(stock_metrics, weights))
    portfolio_vol = np.sqrt(
        sum((m["annual_vol"] ** 2) * (w ** 2) for m, w in zip(stock_metrics, weights))
    )
    
    sharpe_ratio = (portfolio_return - 0.035) / portfolio_vol if portfolio_vol > 0 else 0
    max_drawdown = -portfolio_vol * 1.5
    
    return {
        "expected_annual_return": round(portfolio_return * 100, 2),
        "annual_volatility": round(portfolio_vol * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "benchmark_alpha": round((portfolio_return - 0.08) * 100, 2)
    }


tools = [
    get_stock_prices,
    get_financial_metrics,
    get_technical_signals,
    get_company_info,
    get_stocks_by_sector,
    calculate_portfolio_performance
]


# =====================================================
# Node 함수들 (Graph 구성)
# =====================================================

def initialization_node(state: AgentState) -> AgentState:
    """초기화: 선택된 종목의 기본 정보 수집"""
    print("\n📋 [초기화] 선택된 종목 정보 로드 중...")
    
    tickers = set()
    
    # 섹터별 종목 수집
    if state["investment_targets"].get("sectors"):
        for sector in state["investment_targets"]["sectors"]:
            sector_tickers = [t for t, s in SECTOR_MAP.items() if s == sector]
            tickers.update(sector_tickers)
    
    # 직접 선택한 종목 추가
    if state["investment_targets"].get("tickers"):
        tickers.update(state["investment_targets"]["tickers"])
    
    # 기본 정보 수집
    company_infos = {}
    for ticker in tickers:
        result = get_company_info.invoke({"ticker": ticker})
        if "error" not in result:
            company_infos[ticker] = result
            print(f"  ✓ {result['name']} ({result['sector']})")
    
    state["company_infos"] = company_infos
    
    return state


def data_collection_node(state: AgentState) -> AgentState:
    """데이터 수집: 주가, 재무, 기술적 지표"""
    print("\n📊 [데이터 수집] 주가, 재무, 기술적 지표 수집 중...")
    
    tickers = list(state["company_infos"].keys())
    stock_prices = {}
    financial_metrics = {}
    technical_signals = {}
    
    for ticker in tickers:
        # 주가
        price_result = get_stock_prices.invoke({"ticker": ticker})
        if "error" not in price_result:
            stock_prices[ticker] = price_result
            print(f"  ✓ {ticker}: 주가 데이터 수집")
        
        # 재무
        fin_result = get_financial_metrics.invoke({"ticker": ticker})
        if "error" not in fin_result:
            financial_metrics[ticker] = fin_result
            print(f"  ✓ {ticker}: 재무 지표 수집")
        
        # 기술적 지표
        tech_result = get_technical_signals.invoke({"ticker": ticker})
        if "error" not in tech_result:
            technical_signals[ticker] = tech_result
            print(f"  ✓ {ticker}: 기술적 지표 수집")
    
    state["stock_prices"] = stock_prices
    state["financial_metrics"] = financial_metrics
    state["technical_signals"] = technical_signals
    
    return state


def analysis_node(state: AgentState) -> AgentState:
    """분석: LLM을 통한 포트폴리오 구성 및 분석"""
    print("\n🤖 [분석] LLM 포트폴리오 분석 중...")
    
    llm = get_chat_model("gpt-4o-mini")
    
    # 수집된 데이터를 프롬프트에 포함
    data_summary = json.dumps({
        "company_infos": state["company_infos"],
        "stock_prices": state["stock_prices"],
        "financial_metrics": state["financial_metrics"],
        "technical_signals": state["technical_signals"]
    }, ensure_ascii=False, indent=2)
    
    analysis_prompt = f"""당신은 투자 분석가입니다.

**투자 조건:**
- 투자 예산: {state['budget']:,}원
- 투자 성향: {state['risk_profile']} (안정: 낮은 변동성 선호, 중립: 균형잡힌 접근, 공격: 높은 수익률 추구)
- 투자 기간: {state['investment_period']} (단기: 3개월 이하, 중기: 3개월~1년, 장기: 1년 이상)
{f"- 추가 요구사항: {state['additional_prompt']}" if state.get('additional_prompt') else ""}

**수행할 작업:**
1. 위 투자 조건에 맞춰 선택된 종목들을 분석
2. 예산 범위 내에서 투자 성향과 기간에 적합한 포트폴리오 구성
3. 성과 지표 계산

**⚠️ 중요: JSON 형식 규칙**
- 반드시 ```json 블록으로 감싸세요
- 모든 문자열은 큰따옴표 사용
- 숫자에는 따옴표 없음
- 마지막에 쉼표 없음

**📊 chart_data 필수 구조:**
1. sunburst: 계층형 차트 데이터 (섹터 → 종목)
   - 루트 섹터: {{"name": "섹터명", "value": 비중}}
   - 하위 종목: {{"name": "종목명", "value": 비중, "parent": "섹터명"}}
2. expected_performance: 수익률 예측 차트
   - months: [1, 3, 6, 12] (고정)
   - portfolio: 포트폴리오 예상 수익률
   - benchmark: 벤치마크(KOSPI) 예상 수익률
- 예시:
  ```json
  {{
  "ai_summary": `  삼성전자(45%), NAVER(30%), 한화오션(25%)으로 구성된 포트폴리오로, IT·조선 등 산업을 고르게 분산해 경기순환 리스크를 완화한 중위험·중수익형 전략입니다.
  AI 반도체 수요 확대와 클라우드 인프라 확장으로 삼성전자와 NAVER의 매출 성장세가 지속될 것으로 예상되며, 한화오션은 해운 및 방산 수요 증가에 따른 수주 확대가 기대되어 기술 성장과 경기 방어를 동시에 잡는 균형형 포트폴리오입니다.
  본 조합은 KOSPI 평균 10~12% 대비 연 16~18% 수준의 기대수익률을 목표로 하며, 약 6%p의 초과수익(Alpha) 가능성이 있습니다. 다만, 글로벌 반도체 경기 둔화나 AI 경쟁 심화, 조선 원자재 가격 상승 및 환율 변동이 단기 리스크로 작용할 수 있어 최대 낙폭은 -14% 내외로 예상됩니다.
  투자 전략은 1년을 기준으로 단계적으로 운영됩니다. 1~3개월 차에는 실적 발표 및 AI 반도체 수요 변화를 모니터링하고, 6개월 시점에는 일정 수익 실현과 함께 NAVER 비중 확대를 검토합니다. 12개월 이후에는 경기 회복 국면에 맞춰 삼성전자 중심으로 리밸런싱을 계획하고 있습니다.\n  종합 평가 결과 82점(매수 추천)으로, AI 산업 성장에 따른 장기적 수익성을 노리는 중위험·중수익형 투자자에게 적합한 포트폴리오로 판단됩니다.`,
    "portfolio_allocation": [
      {{
        "ticker": "068270.KS",
        "name": "효성중공업",
        "sector": "전력망",
        "weight": 0.25,
        "amount": 12500000,
        "shares": 1000,
        "current_price": 12500,
        "target_price": 15000,
        "stop_loss": 11000,
        "scores": {{
          "data_analysis": 75,
          "financial": 78,
          "news": 72
        }}
      }}
    ],
    "performance_metrics": {{
      "expected_return": 15.5,
      "max_drawdown": -12.3,
      "sharpe_ratio": 1.2,
      "benchmark_alpha": 5.0
    }},
    "chart_data": {{
      "sunburst": [
        {{"name": "반도체", "value": 0.50}},
        {{"name": "삼성전자", "value": 0.30, "parent": "반도체"}},
        {{"name": "SK하이닉스", "value": 0.20, "parent": "반도체"}},
        {{"name": "전력망", "value": 0.30}},
        {{"name": "효성중공업", "value": 0.30, "parent": "전력망"}},
        {{"name": "바이오", "value": 0.20}},
        {{"name": "셀트리온", "value": 0.20, "parent": "바이오"}}
      ],
      "expected_performance": {{
        "months": [1, 3, 6, 12],
        "portfolio": [2.0, 6.0, 11.0, 15.5],
        "benchmark": [1.0, 3.0, 5.5, 10.0]
      }}
    }}
  }}
  ```

---

{data_summary} 

위 데이터를 바탕으로 분석을 수행하고, 반드시 위의 JSON 형식으로 결과를 제시하세요."""
    
    response = llm.invoke([HumanMessage(content=analysis_prompt)])
    response_text = response.content
    
    print(f"\n[LLM 응답 길이]: {len(response_text)} 글자")
    
    # ⭐ JSON 파싱 (오류 처리 강화)
    json_start = response_text.find("```json")
    json_end = response_text.find("```", json_start + 7)
    
    if json_start == -1 or json_end == -1:
        print(f"❌ JSON 블록 찾기 실패")
        # 기본값으로 반환
        state["ai_summary"] = "분석 결과를 불러올 수 없습니다."
        state["portfolio_allocation"] = []
        state["performance_metrics"] = {}
        state["chart_data"] = {}
        return state
    
    json_str = response_text[json_start+7:json_end].strip()
    
    # ⭐ JSON 유효성 검사 및 수정
    try:
        result = json.loads(json_str)
        print(f"✅ JSON 파싱 성공")
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 파싱 오류: {e}")
        print(f"  오류 위치: line {e.lineno} column {e.colno}")
        print(f"  문제 부분: {json_str[max(0, e.pos-50):e.pos+50]}")
        
        # 시도 1: 작은따옴표를 큰따옴표로 변환
        json_str_fixed = json_str.replace("'", '"')
        try:
            result = json.loads(json_str_fixed)
            print(f"✅ 작은따옴표 변환으로 파싱 성공")
        except json.JSONDecodeError:
            # 시도 2: 후행 쉼표 제거
            json_str_fixed = re.sub(r',(\s*[}\]])', r'\1', json_str_fixed)
            try:
                result = json.loads(json_str_fixed)
                print(f"✅ 후행 쉼표 제거로 파싱 성공")
            except json.JSONDecodeError:
                print(f"❌ JSON 수정 실패 - 기본값으로 반환")
                state["ai_summary"] = "LLM이 유효한 JSON을 생성하지 못했습니다."
                state["portfolio_allocation"] = []
                state["performance_metrics"] = {}
                state["chart_data"] = {}
                return state
    
    # 파싱된 데이터를 상태에 저장
    state["ai_summary"] = result.get("ai_summary", "분석 요약 없음")
    state["portfolio_allocation"] = result.get("portfolio_allocation", [])
    state["performance_metrics"] = result.get("performance_metrics", {})
    state["chart_data"] = result.get("chart_data", {})
    
    print(f"  - portfolio_allocation 개수: {len(state['portfolio_allocation'])}")
    print(f"  - performance_metrics: {state['performance_metrics']}")
    
    return state


def validation_node(state: AgentState) -> AgentState:
    """검증: 포트폴리오 데이터 검증"""
    print("\n✅ [검증] 포트폴리오 데이터 검증 중...")
    
    for stock in state["portfolio_allocation"]:
        ticker = stock.get("ticker")
        if ticker in state["company_infos"]:
            correct_info = state["company_infos"][ticker]
            stock["name"] = correct_info["name"]
            stock["sector"] = correct_info["sector"]
            print(f"  ✓ {ticker}: {correct_info['name']} (검증됨)")
    
    return state


def should_continue(state: AgentState) -> str:
    """정지 조건 검사"""
    if state.get("portfolio_allocation"):
        return "validation"
    return "analysis"


# =====================================================
# Graph 구성
# =====================================================

def build_portfolio_graph():
    """LangGraph 구성"""
    graph = StateGraph(AgentState)
    
    # Node 추가
    graph.add_node("initialization", initialization_node)
    graph.add_node("data_collection", data_collection_node)
    graph.add_node("analysis", analysis_node)
    graph.add_node("validation", validation_node)
    
    # Edge 추가
    graph.set_entry_point("initialization")
    graph.add_edge("initialization", "data_collection")
    graph.add_edge("data_collection", "analysis")
    graph.add_edge("analysis", "validation")
    graph.add_edge("validation", END)
    
    return graph.compile()


# =====================================================
# 실행 함수
# =====================================================

def run_portfolio_agent_langgraph(
    budget: int,
    investment_targets: Dict[str, List[str]],
    risk_profile: str,
    investment_period: str,
    additional_prompt: str = ""
) -> Dict[str, Any]:
    """LangGraph 기반 포트폴리오 분석"""
    
    print(f"\n{'='*60}")
    print(f"🤖 LangGraph 포트폴리오 분석 Agent 시작")
    print(f"{'='*60}")
    
    graph = build_portfolio_graph()
    
    initial_state: AgentState = {
        "budget": budget,
        "investment_targets": investment_targets,
        "risk_profile": risk_profile,
        "investment_period": investment_period,
        "additional_prompt": additional_prompt,
        "company_infos": {},
        "stock_prices": {},
        "financial_metrics": {},
        "technical_signals": {},
        "correlation_data": {},
        "portfolio_allocation": [],
        "performance_metrics": {},
        "chart_data": {},
        "ai_summary": "",
        "messages": [],
        "iteration": 0
    }
    
    final_state = graph.invoke(initial_state)
    
    return {
        "success": True,
        "ai_summary": final_state.get("ai_summary"),
        "portfolio_allocation": final_state.get("portfolio_allocation"),
        "performance_metrics": final_state.get("performance_metrics"),
        "chart_data": final_state.get("chart_data")
    }