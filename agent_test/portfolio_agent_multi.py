"""
portfolio_agent_multi.py

멀티 에이전트 기반 투자 포트폴리오 분석 시스템 (v3)
- 재무 분석 전문가
- 기술 분석 전문가  
- 뉴스 분석 전문가
- Supervisor (코디네이터)
"""

from typing import Any, Dict, List, Optional, TypedDict, Literal, Annotated
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
import operator

import numpy as np

from langgraph.graph import StateGraph, END
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from core.db import fetch_dicts
from core.llm_clients import get_chat_model
from jobs.seed_companies import INDUSTRY_CODE_MAP

# =====================================================
# 멀티 에이전트 State Definition
# =====================================================

class MultiAgentState(TypedDict):
    """멀티 에이전트 시스템의 상태"""
    # 입력 파라미터
    budget: int
    investment_targets: Dict[str, List[str]]
    risk_profile: str
    investment_period: str
    additional_prompt: str
    model_name: str  # ⭐ 사용할 LLM 모델명
    
    # 기본 데이터
    company_infos: Dict[str, Dict[str, Any]]  # ticker -> company info
    stock_prices: Dict[str, Dict[str, Any]]   # ticker -> price data
    financial_metrics: Dict[str, Dict[str, Any]]  # ⭐ 추가: ticker -> financial data
    technical_signals: Dict[str, Dict[str, Any]]  # ⭐ 추가: ticker -> technical signals
    
    # ⭐ 각 전문가 에이전트의 분석 결과
    financial_analysis: Dict[str, Any]        # 재무 분석 전문가 결과
    technical_analysis: Dict[str, Any]        # 기술 분석 전문가 결과
    news_analysis: Dict[str, Any]             # 뉴스 분석 전문가 결과
    
    # Supervisor 관련
    next_agent: str                           # 다음 실행할 에이전트
    discussion_history: List[str]             # ⭐ 일반 리스트로 변경 (supervisor에서만 설정)
    
    # 최종 결과
    portfolio_allocation: List[Dict[str, Any]]
    performance_metrics: Dict[str, Any]
    chart_data: Dict[str, Any]
    ai_summary: str
    
    # 메시지 히스토리
    messages: Annotated[List[BaseMessage], operator.add]  # ⭐ 병렬 업데이트 허용
    iteration: int


# =====================================================
# DB 로드 함수 (기존과 동일)
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


AVAILABLE_STOCKS = load_available_stocks()
SECTOR_MAP = load_sector_map()

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
# Tool 정의 (기존 함수 재사용)
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
    
    return {
        "ticker": ticker,
        "roe": round(roe, 2),
        "opm": round(opm, 2),
        "debt_ratio": round(debt_ratio, 2),
        "revenue_growth_yoy": round(rev_growth, 2),
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
    momentum = to_float(sig.get("momentum_20d", 0)) * 100
    vol = to_float(sig.get("vol_20d", 0))
    ma20 = to_float(sig.get("ma20", 0))
    ma60 = to_float(sig.get("ma60", 0))
    
    return {
        "ticker": ticker,
        "rsi14": round(rsi, 2),
        "momentum_20d": round(momentum, 2),
        "vol_20d": round(vol, 4),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
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


# =====================================================
# 에이전트 노드들
# =====================================================

def initialization_node(state: MultiAgentState) -> MultiAgentState:
    """초기화: 선택된 종목의 기본 정보 및 주가 데이터 수집"""
    print("\n" + "="*60)
    print("🚀 멀티 에이전트 포트폴리오 분석 시작")
    print("="*60)
    print("\n📋 [초기화] 선택된 종목 정보 로드 중...")
    
    tickers = set()
    
    # investment_targets 접근 (Pydantic 모델 또는 dict)
    investment_targets = state["investment_targets"]
    
    # Pydantic 모델인 경우 처리
    if hasattr(investment_targets, 'sectors'):
        sectors = investment_targets.sectors
        ticker_list = investment_targets.tickers
    else:
        sectors = investment_targets.get("sectors", [])
        ticker_list = investment_targets.get("tickers", [])
    
    # 섹터별 종목 수집
    if sectors:
        for sector in sectors:
            sector_tickers = [t for t, s in SECTOR_MAP.items() if s == sector]
            tickers.update(sector_tickers)
    
    # 직접 선택한 종목 추가
    if ticker_list:
        tickers.update(ticker_list)
    
    # 기본 정보, 주가, 재무, 기술적 지표 데이터 수집
    company_infos = {}
    stock_prices = {}
    financial_metrics = {}
    technical_signals = {}
    
    for ticker in tickers:
        # 기업 정보
        info_result = get_company_info.invoke({"ticker": ticker})
        if "error" not in info_result:
            company_infos[ticker] = info_result
            print(f"  ✓ {info_result['name']} ({info_result['sector']})")
            
            # 주가 데이터
            price_result = get_stock_prices.invoke({"ticker": ticker})
            if "error" not in price_result:
                stock_prices[ticker] = price_result
            
            # 재무 지표
            fin_result = get_financial_metrics.invoke({"ticker": ticker})
            if "error" not in fin_result:
                financial_metrics[ticker] = fin_result
            
            # 기술적 지표
            tech_result = get_technical_signals.invoke({"ticker": ticker})
            if "error" not in tech_result:
                technical_signals[ticker] = tech_result
    
    state["company_infos"] = company_infos
    state["stock_prices"] = stock_prices
    state["financial_metrics"] = financial_metrics  # ⭐ 추가
    state["technical_signals"] = technical_signals  # ⭐ 추가
    state["iteration"] = 0
    state["discussion_history"] = []
    state["next_agent"] = "financial_agent"
    
    print(f"\n✅ 초기화 완료: {len(company_infos)}개 종목 로드됨")
    
    return state


def financial_agent_node(state: MultiAgentState) -> MultiAgentState:
    """
    재무 분석 전문가 에이전트
    - ROE, 영업이익률, 부채비율, 매출성장률 분석
    - 재무 건전성 및 수익성 평가
    - 각 종목에 대한 재무 점수 (0-100) 산출
    """
    print("\n" + "="*60)
    print("💰 [재무 분석 전문가] 분석 시작")
    print("="*60)
    
    # ⭐ 상태에서 선택된 모델 사용
    model_name = state.get("model_name", "gpt-4o-mini")
    llm = get_chat_model(model_name)
    print(f"  📌 사용 모델: {model_name}")
    
    # ⭐ 이미 초기화 단계에서 수집된 데이터 활용
    financial_data = state.get("financial_metrics", {})
    stock_prices = state.get("stock_prices", {})
    company_infos = state.get("company_infos", {})
    
    # 주가 정보와 결합
    for ticker, fin_data in financial_data.items():
        if ticker in stock_prices:
            fin_data["current_price"] = stock_prices[ticker].get("current_price")
            fin_data["period_return"] = stock_prices[ticker].get("period_return_pct")
        if ticker in company_infos:
            fin_data["name"] = company_infos[ticker].get("name")
            fin_data["sector"] = company_infos[ticker].get("sector")
        
        print(f"  ✓ {ticker}: ROE {fin_data.get('roe')}%, 부채비율 {fin_data.get('debt_ratio')}%, 현재가 {fin_data.get('current_price', 'N/A')}")
    
    # LLM에게 재무 분석 요청
    prompt = f"""당신은 **재무 분석 전문가**입니다.

**투자 조건:**
- 투자 성향: {state['risk_profile']}
- 투자 기간: {state['investment_period']}

**분석할 종목들:**
{json.dumps(financial_data, ensure_ascii=False, indent=2)}

**임무:**
각 종목에 대해 재무 건전성과 수익성을 평가하고, 0-100점의 **재무 점수**를 산출하세요.

**평가 기준:**
1. ROE (자기자본이익률): 15% 이상 우수 (가중치 30%)
2. OPM (영업이익률): 10% 이상 우수 (가중치 20%)  
3. 부채비율: 100% 이하 우수 (가중치 30%)
4. 매출성장률: 20% 이상 우수 (가중치 20%)

**출력 형식 (반드시 JSON):**
```json
{{
  "analysis_summary": "재무 분석 종합 의견 (2-3줄)",
  "ticker_scores": {{
    "005930.KS": {{
      "financial_score": 85,
      "roe_score": 90,
      "opm_score": 75,
      "debt_score": 85,
      "growth_score": 80,
      "comment": "ROE와 수익성이 우수하나 부채비율 관리 필요"
    }},
    ...
  }},
  "top_picks": ["005930.KS", "035420.KS"],
  "risk_warnings": ["높은 부채비율 종목: ...]
}}
```

**중요:** 반드시 JSON 형식으로만 답변하고, 설명은 JSON 내부에 포함하세요."""

    response = llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content
    
    # JSON 파싱
    try:
        json_start = response_text.find("```json")
        json_end = response_text.find("```", json_start + 7)
        
        if json_start != -1 and json_end != -1:
            json_str = response_text[json_start+7:json_end].strip()
        else:
            json_str = response_text
        
        financial_analysis = json.loads(json_str)
        print(f"\n✅ 재무 분석 완료")
        print(f"  - 분석 종목: {len(financial_analysis.get('ticker_scores', {}))}개")
        print(f"  - Top Picks: {financial_analysis.get('top_picks', [])}")
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 파싱 오류: {e}")
        financial_analysis = {
            "analysis_summary": "재무 분석 파싱 실패",
            "ticker_scores": {},
            "top_picks": [],
            "risk_warnings": []
        }
    
    # ⚠️ 병렬 실행 시 충돌 방지: 자신이 업데이트한 필드만 반환
    print(f"\n📝 [재무 전문가] 분석 완료, summary 저장됨")
    
    return {
        "financial_analysis": financial_analysis
        # ⭐ discussion_history는 supervisor에서 한 번에 수집
    }


def technical_agent_node(state: MultiAgentState) -> MultiAgentState:
    """
    기술 분석 전문가 에이전트
    - RSI, 모멘텀, 변동성 분석
    - 매수/매도 시그널 판단
    - 각 종목에 대한 기술적 점수 (0-100) 산출
    """
    print("\n" + "="*60)
    print("📈 [기술 분석 전문가] 분석 시작")
    print("="*60)
    
    # ⭐ 상태에서 선택된 모델 사용
    model_name = state.get("model_name", "gpt-4o-mini")
    llm = get_chat_model(model_name)
    print(f"  📌 사용 모델: {model_name}")
    
    # ⭐ 이미 초기화 단계에서 수집된 데이터 활용
    technical_data = state.get("technical_signals", {})
    stock_prices = state.get("stock_prices", {})
    company_infos = state.get("company_infos", {})
    
    # 주가 정보와 결합
    for ticker, tech_data in technical_data.items():
        if ticker in stock_prices:
            tech_data["current_price"] = stock_prices[ticker].get("current_price")
            tech_data["period_return"] = stock_prices[ticker].get("period_return_pct")
            tech_data["volatility"] = stock_prices[ticker].get("volatility_annual")
        if ticker in company_infos:
            tech_data["name"] = company_infos[ticker].get("name")
            tech_data["sector"] = company_infos[ticker].get("sector")
        
        print(f"  ✓ {ticker}: RSI {tech_data.get('rsi14')}, 모멘텀 {tech_data.get('momentum_20d')}%")
    
    # LLM에게 기술 분석 요청
    prompt = f"""당신은 **기술 분석 전문가**입니다.

**투자 조건:**
- 투자 성향: {state['risk_profile']}
- 투자 기간: {state['investment_period']}

**분석할 종목들:**
{json.dumps(technical_data, ensure_ascii=False, indent=2)}

**임무:**
각 종목에 대해 기술적 지표를 분석하고, 0-100점의 **기술적 점수**를 산출하세요.

**평가 기준:**
1. RSI (14일): 30-70 범위가 안정적 (가중치 30%)
   - 과매수(>70): 조정 가능성
   - 과매도(<30): 반등 가능성
2. 모멘텀 (20일): 양수면 상승 추세 (가중치 30%)
3. 이동평균선 (MA20/MA60): 현재가와 비교 (가중치 20%)
   - 현재가 > MA20 > MA60: 강한 상승 추세
   - MA20 > 현재가 > MA60: 조정 중
   - MA60 > 현재가: 약세
4. 변동성: 낮을수록 안정적 (가중치 20%)

**출력 형식 (반드시 JSON):**
```json
{{
  "analysis_summary": "기술적 분석 종합 의견 (2-3줄)",
  "ticker_scores": {{
    "005930.KS": {{
      "technical_score": 78,
      "rsi_score": 80,
      "momentum_score": 75,
      "ma_score": 85,
      "volatility_score": 70,
      "signal": "매수",
      "comment": "RSI 안정권, 상승 모멘텀 유지, MA20 돌파"
    }},
    ...
  }},
  "buy_signals": ["005930.KS"],
  "sell_signals": [],
  "hold_signals": ["035420.KS"]
}}
```

**중요:** 반드시 JSON 형식으로만 답변하세요."""

    response = llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content
    
    # JSON 파싱
    try:
        json_start = response_text.find("```json")
        json_end = response_text.find("```", json_start + 7)
        
        if json_start != -1 and json_end != -1:
            json_str = response_text[json_start+7:json_end].strip()
        else:
            json_str = response_text
        
        technical_analysis = json.loads(json_str)
        print(f"\n✅ 기술 분석 완료")
        print(f"  - 분석 종목: {len(technical_analysis.get('ticker_scores', {}))}개")
        print(f"  - 매수 시그널: {technical_analysis.get('buy_signals', [])}")
        print(f"  - 매도 시그널: {technical_analysis.get('sell_signals', [])}")
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 파싱 오류: {e}")
        technical_analysis = {
            "analysis_summary": "기술 분석 파싱 실패",
            "ticker_scores": {},
            "buy_signals": [],
            "sell_signals": [],
            "hold_signals": []
        }
    
    # ⚠️ 병렬 실행 시 충돌 방지: 자신이 업데이트한 필드만 반환
    print(f"\n📝 [기술 전문가] 분석 완료, summary 저장됨")
    
    return {
        "technical_analysis": technical_analysis
        # ⭐ discussion_history는 supervisor에서 한 번에 수집
    }


def news_agent_node(state: MultiAgentState) -> MultiAgentState:
    """
    뉴스 분석 전문가 에이전트
    - 산업 동향 분석
    - 종목별 뉴스 감성 분석 (향후 Qdrant 통합 예정)
    - 각 종목에 대한 뉴스 점수 (0-100) 산출
    """
    print("\n" + "="*60)
    print("📰 [뉴스 분석 전문가] 분석 시작")
    print("="*60)
    
    # ⭐ 상태에서 선택된 모델 사용
    model_name = state.get("model_name", "gpt-4o-mini")
    llm = get_chat_model(model_name)
    print(f"  📌 사용 모델: {model_name}")
    
    company_infos = state.get("company_infos", {})
    stock_prices = state.get("stock_prices", {})
    
    # 섹터별 동향 정보 수집
    sector_trends = {}
    company_data = {}
    for ticker, info in company_infos.items():
        sector = info.get("sector")
        if sector and sector not in sector_trends:
            sector_trends[sector] = INDUSTRY_TRENDS.get(sector, "정보 없음")
        
        # 주가 정보 추가
        company_data[ticker] = {
            "name": info["name"],
            "sector": info["sector"],
            "current_price": stock_prices.get(ticker, {}).get("current_price"),
            "period_return": stock_prices.get(ticker, {}).get("period_return_pct")
        }
    
    # LLM에게 뉴스 분석 요청
    prompt = f"""당신은 **뉴스 및 산업 동향 분석 전문가**입니다.

**투자 조건:**
- 투자 성향: {state['risk_profile']}
- 투자 기간: {state['investment_period']}

**분석할 종목 및 섹터 동향:**
{json.dumps({
    "companies": company_data,
    "sector_trends": sector_trends
}, ensure_ascii=False, indent=2)}

**임무:**
각 종목에 대해 산업 동향과 뉴스 전망을 분석하고, 0-100점의 **뉴스 점수**를 산출하세요.

**평가 기준:**
1. 산업 성장성: 해당 섹터의 장기 성장 전망 (가중치 40%)
2. 정책 지원: 정부 정책 및 규제 환경 (가중치 20%)
3. 시장 수요: 제품/서비스 수요 추세 (가중치 25%)
4. 경쟁 환경: 시장 점유율 및 경쟁 강도 (가중치 15%)

**출력 형식 (반드시 JSON):**
```json
{{
  "analysis_summary": "뉴스 분석 종합 의견 (2-3줄)",
  "ticker_scores": {{
    "005930": {{
      "news_score": 88,
      "industry_growth_score": 90,
      "policy_support_score": 85,
      "market_demand_score": 90,
      "competition_score": 80,
      "sentiment": "positive",
      "comment": "AI 반도체 수요 급증으로 장기 성장 전망 밝음"
    }},
    ...
  }},
  "sector_outlook": {{
    "반도체": "매우 긍정적",
    "바이오": "긍정적"
  }}
}}
```

**중요:** 반드시 JSON 형식으로만 답변하세요."""

    response = llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content
    
    # JSON 파싱
    try:
        json_start = response_text.find("```json")
        json_end = response_text.find("```", json_start + 7)
        
        if json_start != -1 and json_end != -1:
            json_str = response_text[json_start+7:json_end].strip()
        else:
            json_str = response_text
        
        news_analysis = json.loads(json_str)
        print(f"\n✅ 뉴스 분석 완료")
        print(f"  - 분석 종목: {len(news_analysis.get('ticker_scores', {}))}개")
        print(f"  - 섹터 전망: {news_analysis.get('sector_outlook', {})}")
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 파싱 오류: {e}")
        news_analysis = {
            "analysis_summary": "뉴스 분석 파싱 실패",
            "ticker_scores": {},
            "sector_outlook": {}
        }
    
    # ⚠️ 병렬 실행 시 충돌 방지: 자신이 업데이트한 필드만 반환
    print(f"\n📝 [뉴스 전문가] 분석 완료, summary 저장됨")
    
    return {
        "news_analysis": news_analysis
        # ⭐ discussion_history는 supervisor에서 한 번에 수집
    }


def validation_node(state: MultiAgentState) -> MultiAgentState:
    """
    검증 노드: 최종 포트폴리오 데이터 검증 및 교정
    - DB에 없는 ticker 제거
    - ticker, name, sector를 DB 데이터로 강제 교체
    - 현재가 정보 업데이트
    """
    print("\n" + "="*60)
    print("✅ [검증] 최종 포트폴리오 데이터 검증")
    print("="*60)
    
    portfolio = state.get("portfolio_allocation", [])
    company_infos = state.get("company_infos", {})
    stock_prices = state.get("stock_prices", {})
    
    validated_portfolio = []
    total_weight = 0.0
    
    for stock in portfolio:
        ticker = stock.get("ticker")
        
        # ticker가 DB에 존재하는지 확인
        if ticker in company_infos:
            # ✅ DB 데이터로 강제 교체
            stock["ticker"] = ticker
            stock["name"] = company_infos[ticker]["name"]
            stock["sector"] = company_infos[ticker]["sector"]
            
            # 현재가 정보 업데이트
            if ticker in stock_prices:
                db_price = stock_prices[ticker].get("current_price")
                if db_price:
                    stock["current_price"] = db_price
                    # 주식 수 재계산
                    amount = stock.get("amount", 0)
                    if amount > 0 and db_price > 0:
                        stock["shares"] = int(amount / db_price)
            
            total_weight += stock.get("weight", 0)
            validated_portfolio.append(stock)
            print(f"  ✓ {ticker}: {stock['name']} (검증 완료)")
        else:
            print(f"  ⚠️ {ticker}: DB에 없는 종목 (제외됨)")
    
    # 가중치 합계 검증
    if abs(total_weight - 1.0) > 0.05:
        print(f"  ⚠️ 가중치 합계 오류: {total_weight:.2f} (조정 필요)")
        # 가중치 정규화
        if total_weight > 0:
            for stock in validated_portfolio:
                stock["weight"] = stock["weight"] / total_weight
    
    state["portfolio_allocation"] = validated_portfolio
    
    print(f"\n✅ 검증 완료: {len(validated_portfolio)}개 종목")
    
    return state


def supervisor_node(state: MultiAgentState) -> MultiAgentState:
    """
    Supervisor (총괄 매니저) 에이전트
    - 3명의 전문가 의견을 통합
    - 최종 포트폴리오 구성
    - 투자 비중 및 목표가/손절가 설정
    """
    print("\n" + "="*60)
    print("👔 [Supervisor] 전문가 의견 통합 및 최종 포트폴리오 구성")
    print("="*60)
    
    # ⭐ 상태에서 선택된 모델 사용 (Supervisor도 동일 모델 사용)
    model_name = state.get("model_name", "gpt-4o-mini")
    llm = get_chat_model(model_name)
    print(f"  📌 사용 모델: {model_name}")
    
    # 3명의 전문가 의견 수집
    financial = state.get("financial_analysis", {})
    technical = state.get("technical_analysis", {})
    news = state.get("news_analysis", {})
    
    # ⭐ 종목별 정확한 섹터명 정보 추출
    company_infos = state.get("company_infos", {})
    ticker_sector_map = {}
    for ticker, info in company_infos.items():
        ticker_sector_map[ticker] = {
            "name": info.get("name"),
            "sector": info.get("sector")  # DB의 정확한 섹터명
        }
    
    # ⭐ 디버깅: supervisor 실행 횟수 추적
    current_history = state.get("discussion_history", [])
    print(f"\n� [Supervisor 디버깅] discussion_history 개수: {len(current_history)}")
    
    print("\n�📊 전문가 의견 요약:")
    for idx, msg in enumerate(current_history, 1):
        print(f"  [{idx}] {msg[:80]}...")
    
    print(f"\n📋 종목-섹터 매핑:")
    for ticker, data in ticker_sector_map.items():
        print(f"  - {ticker}: {data['name']} → 섹터: {data['sector']}")
    
    # Supervisor 프롬프트
    prompt = f"""당신은 **투자 포트폴리오 매니저 (Supervisor)**입니다.
3명의 전문가가 종목을 분석했습니다. 이들의 의견을 종합하여 최종 포트폴리오를 구성하세요.

**투자 조건:**
- 투자 예산: {state['budget']:,}원
- 투자 성향: {state['risk_profile']} (안정: 낮은 변동성 선호, 중립: 균형잡힌 접근, 공격: 높은 수익률 추구)
- 투자 기간: {state['investment_period']} (단기: 3개월 이하, 중기: 3개월~1년, 장기: 1년 이상)
{f"- 추가 요구사항: {state['additional_prompt']}" if state.get('additional_prompt') else ""}

**⚠️ 중요: 종목-섹터 매핑 (반드시 이 섹터명을 사용)**
{json.dumps(ticker_sector_map, ensure_ascii=False, indent=2)}

**전문가 분석 결과:**

1️⃣ 재무 분석 전문가:
{json.dumps(financial, ensure_ascii=False, indent=2)}

2️⃣ 기술 분석 전문가:
{json.dumps(technical, ensure_ascii=False, indent=2)}

3️⃣ 뉴스 분석 전문가:
{json.dumps(news, ensure_ascii=False, indent=2)}

**수행할 작업:**
1. 위 투자 조건에 맞춰 선택된 종목들을 분석
2. 예산 범위 내에서 투자 성향과 기간에 적합한 포트폴리오 구성
3. 성과 지표 계산

**📊 chart_data 필수 구조:**
1. sunburst: 계층형 차트 데이터 (섹터 → 종목)
   - ⚠️ **섹터명은 위 "종목-섹터 매핑"에 있는 sector 값을 정확히 사용**
   - 루트 섹터: {{"name": "섹터명", "value": 비중}}
   - 하위 종목: {{"name": "종목명", "value": 비중, "parent": "섹터명"}}
2. expected_performance: 수익률 예측 차트
   - months: [1, 3, 6, 12] (고정)
   - portfolio: 포트폴리오 예상 수익률
   - benchmark: 벤치마크(KOSPI) 예상 수익률
- 예시:
  ```json
  {{
  "ai_summary": `  삼성전자(45%), NAVER(30%), 한화오션(25%)으로 구성된 포트폴리오로, IT·조선 등 산업을 고르게 분산해 경기순환 리스크를 완화한 중립형 전략입니다.
  투자 전략은 1년을 기준으로 단계적으로 운영됩니다. 1~3개월 차에는 실적 발표 및 AI 반도체 수요 변화를 모니터링하고, 6개월 시점에는 일정 수익 실현과 함께 NAVER 비중 확대를 검토합니다. 
  12개월 이후에는 경기 회복 국면에 맞춰 삼성전자 중심으로 리밸런싱을 계획하고 있습니다.  종합 평가 결과 82점으로, AI 산업 성장에 따른 장기적 수익성을 노리는 중립형 투자자에게 적합한 포트폴리오로 판단됩니다.`,
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

반드시 위의 JSON 형식으로 결과를 제시하세요."""

    response = llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content
    
    # JSON 파싱
    try:
        json_start = response_text.find("```json")
        json_end = response_text.find("```", json_start + 7)
        
        if json_start != -1 and json_end != -1:
            json_str = response_text[json_start+7:json_end].strip()
        else:
            json_str = response_text
        
        # JSON 정리
        json_str_fixed = json_str.replace("'", '"')
        json_str_fixed = re.sub(r',(\s*[}\]])', r'\1', json_str_fixed)
        
        result = json.loads(json_str_fixed)
        
        state["ai_summary"] = result.get("ai_summary", "")
        state["portfolio_allocation"] = result.get("portfolio_allocation", [])
        state["performance_metrics"] = result.get("performance_metrics", {})
        state["chart_data"] = result.get("chart_data", {})
        
        print(f"\n✅ Supervisor 분석 완료")
        print(f"  - 포트폴리오 생성: {len(state['portfolio_allocation'])}개 종목")
        print(f"  - 예상 수익률: {state['performance_metrics'].get('expected_return', 0)}%")
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 파싱 오류: {e}")
        state["ai_summary"] = "최종 포트폴리오 생성 실패"
        state["portfolio_allocation"] = []
        state["performance_metrics"] = {}
        state["chart_data"] = {}
    
    # ⭐ discussion_history 설정 (3명의 전문가 의견을 한 번에 수집)
    discussion_history = []
    
    if financial.get('analysis_summary'):
        discussion_history.append(f"[재무 전문가] {financial['analysis_summary']}")
    
    if technical.get('analysis_summary'):
        discussion_history.append(f"[기술 전문가] {technical['analysis_summary']}")
    
    if news.get('analysis_summary'):
        discussion_history.append(f"[뉴스 전문가] {news['analysis_summary']}")
    
    state["discussion_history"] = discussion_history
    print(f"\n📝 [Supervisor] discussion_history 설정 완료: {len(discussion_history)}개")
    
    return state


# =====================================================
# 멀티 에이전트 그래프 구성
# =====================================================

def aggregator_node(state: MultiAgentState) -> MultiAgentState:
    """
    병렬 실행된 전문가 노드들의 결과를 집계하는 대기 노드
    LangGraph가 모든 전문가 노드 완료를 기다림 (barrier 역할)
    """
    print("\n" + "="*60)
    print("🔄 [집계 노드] 3명의 전문가 분석 완료, Supervisor로 전달")
    print("="*60)
    return {}  # 상태 변경 없음, 단순 통과


def build_multi_agent_graph():
    """
    멀티 에이전트 그래프 구성
    
    구조:
    initialization
        ↓
    [financial_agent | technical_agent | news_agent] (병렬 실행)
        ↓
    aggregator (barrier: 3개 노드 완료 대기)
        ↓
    supervisor (1번만 실행, LLM 호출 1회)
        ↓
    validation (검증)
        ↓
    END
    """
    graph = StateGraph(MultiAgentState)
    
    # 노드 추가
    graph.add_node("initialization", initialization_node)
    graph.add_node("financial_agent", financial_agent_node)
    graph.add_node("technical_agent", technical_agent_node)
    graph.add_node("news_agent", news_agent_node)
    graph.add_node("aggregator", aggregator_node)  # ⭐ barrier 노드
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("validation", validation_node)
    
    # 엣지 구성
    graph.set_entry_point("initialization")
    
    # ⭐ 3명의 전문가는 병렬로 실행 (순서 무관)
    graph.add_edge("initialization", "financial_agent")
    graph.add_edge("initialization", "technical_agent")
    graph.add_edge("initialization", "news_agent")
    
    # ⭐ 3명 모두 aggregator로 (LangGraph가 모두 완료될 때까지 대기)
    graph.add_edge("financial_agent", "aggregator")
    graph.add_edge("technical_agent", "aggregator")
    graph.add_edge("news_agent", "aggregator")
    
    # ⭐ aggregator → supervisor (1번만 실행!)
    graph.add_edge("aggregator", "supervisor")
    
    # Supervisor 완료 후 검증
    graph.add_edge("supervisor", "validation")  # ⭐ 수정
    
    # 검증 완료 후 종료
    graph.add_edge("validation", END)  # ⭐ 추가
    
    return graph.compile()


# =====================================================
# 실행 함수
# =====================================================

def run_multi_agent_portfolio(
    budget: int,
    investment_targets: Dict[str, List[str]],
    risk_profile: str,
    investment_period: str,
    additional_prompt: str = "",
    model_name: str = None  # ⭐ 모델 선택 파라미터 추가
) -> Dict[str, Any]:
    """멀티 에이전트 포트폴리오 분석 실행"""
    
    print(f"\n{'='*60}")
    print(f"🤖 멀티 에이전트 포트폴리오 분석 시작")
    print(f"{'='*60}")
    
    graph = build_multi_agent_graph()
    
    # ⭐ model_name이 없으면 기본값 사용
    if not model_name:
        from core.llm_clients import AVAILABLE_MODELS
        model_name = AVAILABLE_MODELS[0] if AVAILABLE_MODELS else "gpt-4o-mini"
    
    print(f"🔧 사용 모델: {model_name}")
    
    initial_state: MultiAgentState = {
        "budget": budget,
        "investment_targets": investment_targets,
        "risk_profile": risk_profile,
        "investment_period": investment_period,
        "additional_prompt": additional_prompt,
        "model_name": model_name,  # ⭐ 모델명 추가
        
        "company_infos": {},
        "stock_prices": {},
        "financial_metrics": {},  # ⭐ 추가
        "technical_signals": {},  # ⭐ 추가
        
        "financial_analysis": {},
        "technical_analysis": {},
        "news_analysis": {},
        
        "next_agent": "",
        "discussion_history": [],
        
        "portfolio_allocation": [],
        "performance_metrics": {},
        "chart_data": {},
        "ai_summary": "",
        
        "messages": [],
        "iteration": 0
    }
    
    final_state = graph.invoke(initial_state)
    
    print(f"\n{'='*60}")
    print(f"✅ 멀티 에이전트 분석 완료!")
    print(f"{'='*60}\n")
    
    return {
        "success": True,
        "ai_summary": final_state.get("ai_summary"),
        "portfolio_allocation": final_state.get("portfolio_allocation"),
        "performance_metrics": final_state.get("performance_metrics"),
        "chart_data": final_state.get("chart_data"),
        "discussion_history": final_state.get("discussion_history")
    }


# =====================================================
# 테스트 코드
# =====================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 멀티 에이전트 시스템 테스트")
    print("="*60)
    
    test_request = {
        "budget": 50000000,  # 5천만원
        "investment_targets": {
            "sectors": ["반도체"],
            "tickers": []
        },
        "risk_profile": "중립",
        "investment_period": "장기",
        "additional_prompt": "AI 반도체 관련 종목 선호"
    }
    
    result = run_multi_agent_portfolio(**test_request)
    
    if result["success"]:
        print("\n" + "="*60)
        print("📊 최종 결과")
        print("="*60)
        print(f"\n💡 AI 요약:\n{result['ai_summary']}\n")
        print(f"📈 포트폴리오: {len(result['portfolio_allocation'])}개 종목")
        print(f"📉 예상 수익률: {result['performance_metrics'].get('expected_return', 0)}%")


print("\n✅ Step 6 완료: 멀티 에이전트 그래프 구성 완료")
print("\n🎉 모든 단계 완료! 멀티 에이전트 시스템이 준비되었습니다.")
print("\n실행 방법:")
print("  python agent_test/portfolio_agent_multi.py")
