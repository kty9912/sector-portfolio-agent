import os
import operator
from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

# 'llm_clients'는 'agents.tools'보다 먼저 임포트되어야 할 수 있습니다. (의존성 순서)
from core.llm_clients import get_chat_model, AVAILABLE_MODELS
from agents.tools import available_tools # agents/tools.py에서 툴 목록을 가져옵니다.

# --- 1. Graph State 정의 ---
# LangGraph가 노드 간에 전달할 '작업 가방' (상태)
class AgentState(TypedDict):
    sector_name: str  # 섹터 이름
    stock_tickers: List[str] # 종목 리스트
    total_budget: float  # 총 투자 예산
    risk_preference: str # 위험 선호도
    investment_period: str # 투자 기간(단기,중기,장기)
    ai_model: str      # 사용할 LLM 모델 이름
    additional_prompt: str # 추가 사용자 프롬프트
    messages: Annotated[List[BaseMessage], operator.add] # 대화 기록 (메시지 누적)
    iteration_count: int # 7회 루프 제한을 위한 카운터
    # 툴 실행 결과를 저장할 '빈 상자'들
    momentum_result: dict
    realtime_news_result: List[Dict] # Tavily 결과
    historical_news_result: dict      # Qdrant/Firecrawl 결과
    financial_data_result: dict  # 재무 데이터 (팀원 담당)
    technical_analysis_result: dict  # 기술적 분석 (팀원 담당)
    
    # === 점수화 결과 ===
    data_analysis_score: float  # 데이터분석 점수
    financial_score: float  # 재무점수
    news_score: float  # 뉴스점수
    
    # === 최종 출력 ===
    portfolio_allocation: Dict[str, float]  # 종목별 비중
    target_prices: Dict[str, Dict]  # 목표가, 손절가
    performance_metrics: dict  # 수익률, MDD, 샤프비율
    # 최종 결과물
    final_report: str

# --- 2. Graph Nodes (노드) 정의 ---

def create_graph_engine(model_name: str, recursion_limit: int = 7):
    """
    지정된 LLM 모델 이름으로 LangGraph 엔진(컴파일된 앱)을 생성합니다.
    """
    
    # 1. LLM 팩토리에서 선택된 LLM을 가져옵니다.
    llm = get_chat_model(model_name)
    
    # 2. LLM에게 '연장(Tool) 사용법 메뉴얼'을 바인딩합니다.
    llm_with_tools = llm.bind_tools(available_tools)

    # --- 3. 노드 함수 정의 ---

    # (Agent 1: 코디네이터 역할)
    # LLM이 어떤 툴을 호출할지 결정하거나, 보고서를 생성할지 결정하는 노드
    def coordinator_node(state: AgentState):
        print(f"\n--- [Graph] Node: Coordinator (Step {state['iteration_count'] + 1}/{recursion_limit}) ---")
        
        # 1. 현재 반복 횟수를 +1 합니다. (0부터 시작)
        state['iteration_count'] += 1
        
        # 2. LLM에게 현재 상황과 루프 횟수를 알려주고 다음 행동을 결정하게 합니다.
        prompt = f"""
        당신은 7단계(max_iterations) 안에 임무를 완수해야 하는 금융 분석 코디네이터입니다.
        현재 {state['iteration_count']}번째 단계입니다. 남은 단계: {recursion_limit - state['iteration_count']}
        사용자가 요청한 섹터: '{state['sector_name']}'
        지금까지의 대화 기록:  {state['messages']}
        
        수집된 데이터 현황:
        - 모멘텀 분석: {state.get('momentum_result', '아직 분석 안됨')}
        - 실시간 뉴스 (Tavily): {state.get('realtime_news_result', '아직 분석 안됨')}
        - 과거/심층 뉴스 (Qdrant): {state.get('historical_news_result', '아직 분석 안됨')}

        다음 행동을 결정하세요.
        1. 만약 *모든* 데이터 (모멘텀, Tavily, Qdrant)가 수집되었다면, 'report_generator_node'를 호출하세요.
        2. 만약 데이터가 덜 끝났다면, 필요한 툴을 *모두* 호출하세요.
           (예: 'get_sector_etf_momentum', 'search_realtime_news_tavily', 'ingest_and_search_qdrant' 툴)
        """
        
        # Tavily 검색 쿼리를 더 구체적으로 만듭니다.
        tavily_query = f"{state['sector_name']} sector latest news summary"
        qdrant_query = state['sector_name']

        # [업그레이드] 3개의 툴을 모두 호출하도록 프롬프트 구성
        # (더 나은 방식은 LLM이 스스로 판단하게 하는 것이지만, MVP는 명시적으로 호출)
        initial_prompt = f"""
        '{state['sector_name']}' 섹터 분석을 시작합니다.
        아래 3개의 툴을 *모두* 호출하여 데이터를 수집하세요:
        1. get_sector_etf_momentum(sector_name="{state['sector_name']}")
        2. search_realtime_news_tavily(query="{tavily_query}")
        3. search_sector_news_qdrant(sector_name="{qdrant_query}")
        
        모든 툴 호출이 끝나면, 수집된 정보로 보고서를 생성하세요.
        """
        
        # 첫 번째 스텝에서는 3개의 툴을 모두 호출하도록 유도
        if state['iteration_count'] == 1:
            messages = [HumanMessage(content=initial_prompt)]
        else:
            messages = state['messages'] + [HumanMessage(content=prompt)]

        response = llm_with_tools.invoke(messages)
        # Persist the updated iteration count so LangGraph will update AgentState
        # (fixes the "memory loss" bug where iteration_count was not returned)
        return {"messages": [response], "iteration_count": state['iteration_count']}

    # (Agent 2, 5 등)
    # 실제 툴을 실행하는 노드
    def tool_executor_node(state: AgentState):
        print(f"\n--- [Graph] Node: Tool Executor (Step {state['iteration_count']}) ---")
        
        last_message = state["messages"][-1]
        
        # tool_calls가 없는 경우 (LLM이 툴을 부르지 않음)
        if not last_message.tool_calls:
            print("  > PM이 툴을 호출하지 않았습니다. (보고서 생성 단계로 이동)")
            return {} # 아무것도 안하고 다음 단계로 (라우터가 처리)

        tool_calls = last_message.tool_calls
        tool_messages = []

        # [업그레이드] 툴 실행 결과를 AgentState에 명시적으로 저장
        momentum_result = state.get("momentum_result")
        realtime_news_result = state.get("realtime_news_result")
        historical_news_result = state.get("historical_news_result")

        for call in tool_calls:
            tool_name = call["name"]
            tool_args = call["args"]
            print(f"  > Executing Tool: {tool_name}({tool_args})")
            
            # `available_tools` 리스트에서 이름으로 함수를 찾습니다.
            found_tool = False
            for t in available_tools:
                if t.name == tool_name:
                    try:
                        # 툴(Python 함수)을 *진짜로* 실행합니다.
                        result = t.invoke(tool_args)
                        
                        # 툴 실행 결과를 AgentState의 올바른 '상자'에 저장
                        if tool_name == "get_sector_etf_momentum":
                            momentum_result = result
                        elif tool_name == "search_realtime_news_tavily":
                            realtime_news_result = result
                        elif tool_name == "search_sector_news_qdrant":
                            historical_news_result = result
                            
                        tool_messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
                        found_tool = True
                        break

                    except Exception as e:
                        print(f"  > Tool Execution Error: {e}")
                        tool_messages.append(ToolMessage(content=f"Error: {e}", tool_call_id=call["id"]))
            
            if not found_tool:
                print(f"  > Tool Not Found Error: {tool_name}")
                tool_messages.append(ToolMessage(content=f"Error: Tool '{tool_name}' not found.", tool_call_id=call["id"]))

        # [업그레이드] 툴 실행 결과를 'messages'와 'AgentState'에 모두 업데이트
        return {
            "messages": tool_messages,
            "momentum_result": momentum_result,
            "realtime_news_result": realtime_news_result,
            "historical_news_result": historical_news_result
        }
    
    def financial_analyzer_node(state: AgentState):
        """
        (Agent 3) PostgreSQL에서 재무 데이터 가져오기
        """
        print(f"\n--- [Graph] Node: Financial Analyzer ---")
        
        from core.db import fetch_dicts
        
        results = {}
        for ticker in state.get('stock_tickers', []):
            # 테이블 구조에 맞게 쿼리 수정 필요
            sql = """
                SELECT ticker, revenue, net_income, debt_ratio, roe
                FROM financial_statements
                WHERE ticker = %s
                ORDER BY report_date DESC
                LIMIT 1
            """
            data = fetch_dicts(sql, [ticker])
            if data:
                results[ticker] = data[0]
        
        return {"financial_data_result": results}

    def portfolio_optimizer_node(state: AgentState):
        """
        (Agent 6) 포트폴리오 최적화 및 비중 계산
        """
        print(f"\n--- [Graph] Node: Portfolio Optimizer ---")
        
        # 수집된 데이터 기반으로 점수 계산
        scores = calculate_comprehensive_scores(state)
        
        # 위험성향에 따른 포트폴리오 비중 계산
        allocation = optimize_portfolio(
            scores=scores,
            risk_preference=state['risk_preference'],
            total_budget=state['total_budget']
        )
        
        return {
            "portfolio_allocation": allocation,
            "data_analysis_score": scores['data_score'],
            "financial_score": scores['financial_score'],
            "news_score": scores['news_score']
        }

    def performance_calculator_node(state: AgentState):
        """
        (Agent 7) 성과 지표 계산 (예상 수익률, MDD, 샤프비율)
        """
        print(f"\n--- [Graph] Node: Performance Calculator ---")
        
        metrics = calculate_performance_metrics(
            allocation=state['portfolio_allocation'],
            investment_period=state['investment_period'],
            historical_data=state['momentum_result']
        )
        
        # 목표가, 손절가 계산
        target_prices = calculate_target_prices(
            state['stock_tickers'],
            state['risk_preference']
        )
        
        return {
            "performance_metrics": metrics,
            "target_prices": target_prices
        }


    # (Agent 7: 보고서 생성기 역할)
    def report_generator_node(state: AgentState):
        print(f"\n--- [Graph] Node: Report Generator (Step {state['iteration_count']}) ---")
        
        # AgentState에서 최종 데이터를 가져옴
        momentum = state.get("momentum_result", "데이터 없음")
        tavily_news = state.get("realtime_news_result", "데이터 없음")
        qdrant_news = state.get("historical_news_result", "데이터 없음")
        
        prompt = f"""
        '{state['sector_name']}' 섹터에 대한 분석이 완료되었습니다.
        아래 3가지 핵심 데이터를 바탕으로, 전문적인 투자 분석 요약 보고서를 작성하세요.

        1. 모멘텀 분석 (yfinance):
        {momentum}

        2. 실시간 속보 (Tavily):
        {tavily_news}
        
        3. 과거/심층 뉴스 (Qdrant/Firecrawl):
        {qdrant_news}
        
        [최종 보고서]
        (3가지 데이터를 모두 종합하여 보고서 형식으로 요약)
        """
        
        response = llm.invoke(prompt) 
        report_text = response.content
        print(f"  > Final Report Generated: {report_text[:100]}...")
        
        return {"final_report": report_text}


    # --- 4. Graph Edges (엣지/경로) 정의 ---
    def router_node(state: AgentState):
        """
        이 노드는 PM(Coordinator)의 마지막 메시지를 보고,
        다음으로 '툴 실행'으로 갈지, '보고서 생성'으로 갈지 결정하는 '이정표'입니다.
        """
        print(f"\n--- [Graph] Node: Router (Step {state['iteration_count']}) ---")
        
        # 1. 7회 루프 제한에 도달했는지 확인
        if state['iteration_count'] >= recursion_limit:
            print("  > 7회 반복 도달. 보고서 생성으로 강제 이동.")
            return "generate_report"
        
        # 2. PM(Coordinator)이 툴을 호출했는지, 아니면 그냥 말했는지 확인
        last_message = state["messages"][-1]
        if isinstance(last_message, ToolMessage) or (last_message.tool_calls):
            # 툴 실행 결과를 바탕으로 PM(Coordinator)이 다시 생각해야 함
            print("  > 툴 실행 완료. PM(Coordinator)이 다음 스텝 결정.")
            return "execute_tools"
        else:
            # PM이 툴 호출 없이 일반 텍스트로 응답 (보고서 생성 결정)
            print("  > PM이 툴 호출 안함. 보고서 생성으로 이동.")
            return "generate_report"

    # --- 5. Graph Workflow (워크플로우) 정의 ---
    workflow = StateGraph(AgentState)
    
    # 5-1. 노드(작업대)들을 공장에 추가
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("financial_analyzer", financial_analyzer_node) 
    workflow.add_node("portfolio_optimizer", portfolio_optimizer_node) 
    workflow.add_node("performance_calculator", performance_calculator_node)
    workflow.add_node("report_generator", report_generator_node)
    
    # 5-2. 엣지(컨베이어 벨트) 연결
    workflow.set_entry_point("coordinator") # "PM 작업대"에서 시작
    
    # [업그레이드된 라우팅]
    # 'coordinator'가 끝나면 'router_node'가 아니라,
    # 'coordinator'가 툴을 불렀는지 아닌지를 'router_node' 함수로 판단
    workflow.add_conditional_edges(
        "coordinator", # "PM 작업대"가 끝난 직후에
        router_node,   # "router_node 함수"를 실행해서 (PM의 마지막 메시지를 보고)
        {
            # 만약 "execute_tools"를 반환하면 -> "tool_executor" 작업대로 감
            "execute_tools": "tool_executor",
            "analyze_financials": "financial_analyzer",
            # 만약 "generate_report"를 반환하면 -> "report_generator" 작업대로 감
            "generate_report": "portfolio_optimizer"
        }
    )
    
    # "툴 실행 작업대"가 끝나면 -> 다시 "PM 작업대"로 돌아가서 다음 스텝 결정 (루프)
    workflow.add_edge("tool_executor", "coordinator")
    workflow.add_edge("financial_analyzer", "portfolio_optimizer")
    workflow.add_edge("portfolio_optimizer", "performance_calculator")
    workflow.add_edge("performance_calculator", "report_generator")
    
    # "보고서 생성 작업대"가 끝나면 -> 공장 밖으로 "종료"
    workflow.add_edge("report_generator", END)

    # --- 6. Graph Compile (컴파일) ---
    app_engine = workflow.compile()
    return app_engine

# --- [엔진 맵 빌더] ---
# FastAPI가 시작될 때, 사용 가능한 모든 모델에 대해
# LangGraph 엔진을 *미리* 컴파일해서 '지도(map)'에 저장해 둡니다.
print("\n--- [Graph] LangGraph 엔진 맵 컴파일 시작... ---")
compiled_engine_map: Dict[str, Any] = {}

# 'AVAILABLE_MODELS'는 'core.llm_clients'에서 임포트한, 
# API 키 존재 여부와 *상관없는* 전체 모델 이름 리스트입니다.
for model_name in AVAILABLE_MODELS:
    try:
        # get_chat_model 함수는 API 키가 없으면 'ValueError'를 발생시킵니다.
        # 따라서, API 키가 있는 모델만 엔진이 컴파일됩니다.
        print(f"  > '{model_name}' 모델의 엔진을 컴파일합니다...")
        # 7회 루프 제한을 하드코딩하여 엔진 생성
        engine = create_graph_engine(model_name=model_name, recursion_limit=7)
        compiled_engine_map[model_name] = engine
        print(f"  > '{model_name}' 엔진 컴파일 성공.")
    except ValueError as e:
        # API 키가 없어서 get_chat_model이 실패한 경우
        print(f"  > '{model_name}' 엔진 컴파일 *건너뛰기*: (원인: {e})")
    except Exception as e:
        # 그 외 다른 이유로 컴파일에 실패한 경우
        print(f"  > !!! '{model_name}' 엔진 컴파일 *실패*: {e} !!!")

print("--- [Graph] LangGraph 엔진 맵 컴파일 완료 ---")
print(f"--- [Graph] 총 {len(compiled_engine_map)}개의 엔진이 준비되었습니다: {list(compiled_engine_map.keys())} ---")