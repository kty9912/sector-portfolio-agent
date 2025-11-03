from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import BaseMessage

from agents.tools import available_tools
from core.llm_clients import get_chat_model

# --- 1. Graph State 정의 ---
# LangGraph가 노드 간에 전달할 '작업 가방' (상태)
class AgentState(TypedDict):
    # 입력: 분석할 섹터 이름
    sector_name: str
    
    # LangGraph가 내부적으로 사용할 메시지 히스토리
    messages: Annotated[List[BaseMessage], operator.add]
    
    # 툴 실행 결과가 여기에 저장됨
    momentum_result: dict
    news_rag_result: dict
    
    # 최종 보고서
    final_report: str

# --- 2. Graph Nodes (노드) 정의 ---
# 노드 = 그래프의 '작업 단계' (우리의 에이전트들)

def create_graph_engine():
    """
    LangGraph 엔진을 생성하고 컴파일하는 팩토리 함수
    """
    
    # 1. 사용할 LLM 가져오기 (Upstage 'solar-pro2' 또는 OpenAI 등)
    # .env의 LLM_PROVIDER="upstage" 설정을 읽어옵니다.
    llm = get_chat_model()
    
    # LangChain의 @tool을 LLM이 사용할 수 있도록 바인딩
    llm_with_tools = llm.bind_tools(available_tools)
    
    # 2. 노드 함수 정의
    
    # (Agent 1: 코디네이터 역할)
    # LLM이 어떤 툴을 호출할지 결정하는 노드
    def coordinator_node(state: AgentState):
        print("\n--- [Graph] Node: Coordinator ---")
        # 현재 상태를 기반으로 LLM이 다음 할 일을 결정 (툴 호출)
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # (Agent 2, 5 등)
    # 실제 툴을 실행하는 노드
    tool_node = ToolNode(available_tools)

    # (Agent 7: 보고서 생성기 역할)
    # 모든 툴 결과를 취합하여 최종 보고서를 작성하는 노드
    def report_generator_node(state: AgentState):
        print("\n--- [Graph] Node: Report Generator ---")
        # 툴 실행 결과를 모두 가져옴
        momentum = state.get("momentum_result", {})
        news = state.get("news_rag_result", {})
        
        # Upstage('solar-pro2') LLM에게 최종 보고서 작성을 요청
        prompt = f"""
        당신은 전문 금융 분석가입니다.
        '{state['sector_name']}' 섹터에 대한 분석이 완료되었습니다.
        아래 데이터를 바탕으로 3문장으로 요약 보고서를 작성해주세요.

        1. 모멘텀 분석 (Agent 2):
        {momentum}

        2. 뉴스 RAG 분석 (Agent 5):
        {news}
        
        최종 요약 보고서:
        """
        
        response = llm.invoke(prompt)
        report_text = response.content
        print(f"--- [Graph] 최종 보고서 생성 완료 ---")
        
        return {"final_report": report_text}

    # 툴 실행 결과를 AgentState의 올바른 위치에 저장하는 함수
    def handle_tool_call(state: AgentState):
        print("\n--- [Graph] Tool Call Handler ---")
        # 마지막 메시지(툴 호출 요청)를 가져옴
        tool_calls = state["messages"][-1].tool_calls
        if tool_calls:
            # 툴 노드를 실행 (yfinance, qdrant 등)
            tool_state = tool_node.invoke(tool_calls)
            
            # 툴 실행 결과를 상태에 저장
            # (이 로직은 툴 개수가 많아지면 더 정교하게 수정 필요)
            for tool_call_result in tool_state:
                if tool_call_result["tool_call_id"] == tool_calls[0]["id"]:
                    if tool_calls[0]["name"] == "get_sector_etf_momentum":
                        state["momentum_result"] = tool_call_result["output"]
                if tool_call_result["tool_call_id"] == tool_calls[1]["id"]:
                    if tool_calls[1]["name"] == "search_sector_news_rag":
                        state["news_rag_result"] = tool_call_result["output"]
            
            return tool_state
    
    # --- 3. Graph Workflow (워크플로우) 정의 ---
    # 그래프(작업 순서)를 설계합니다.
    
    workflow = StateGraph(AgentState)
    
    # 1. 'coordinator' 노드를 추가
    workflow.add_node("coordinator", coordinator_node)
    
    # 2. 'tools' 노드를 추가 (툴 실행)
    workflow.add_node("tool_executor", handle_tool_call)

    # 3. 'report_generator' 노드를 추가 (최종 보고서)
    workflow.add_node("report_generator", report_generator_node)

    # --- 4. Graph Edges (엣지) 정의 ---
    # 노드 간의 연결(작업 순서)을 정의합니다.
    
    # 1. 시작점(Entry Point)은 'coordinator'
    workflow.set_entry_point("coordinator")
    
    # 2. 'coordinator' 노드 실행 후:
    workflow.add_edge("coordinator", "tool_executor")
    
    # 3. 'tool_executor' 노드 실행 후:
    workflow.add_edge("tool_executor", "report_generator")

    # 4. 'report_generator' 노드 실행 후:
    workflow.add_edge("report_generator", END) # 그래프 종료

    # --- 5. Graph Compile (컴파일) ---
    print("\n--- [Graph] LangGraph 엔진 컴파일 중... ---")
    app_engine = workflow.compile()
    print("--- [Graph] LangGraph 엔진 컴파일 완료 ---")
    
    return app_engine

# 엔진을 생성하여 내보내기
# (FastAPI 서버가 이 'compiled_engine'을 임포트해서 사용)
compiled_engine = create_graph_engine()
