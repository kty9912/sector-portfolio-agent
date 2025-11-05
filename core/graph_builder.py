import os
import operator
from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

# 'llm_clients'는 'agents.tools'보다 먼저 임포트되어야 할 수 있습니다. (의존성 순서)
from core.llm_clients import get_chat_model, AVAILABLE_MODELS
from agents.tools import available_tools # agents/tools.py에서 툴 목록을 가져옵니다.

# --- 1. Graph State 정의 ---
# LangGraph가 노드 간에 전달할 '작업 가방' (상태)
class AgentState(TypedDict):
    sector_name: str
    messages: Annotated[List[BaseMessage], operator.add]
    iteration_count: int # 7회 루프 제한을 위한 카운터
    # 툴 실행 결과를 저장할 '빈 상자'들
    momentum_result: dict
    news_rag_result: dict
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
        
        지금까지의 대화 기록:
        {state['messages']}
        
        수집된 데이터 현황:
        - 모멘텀 분석: {state.get('momentum_result', '아직 분석 안됨')}
        - 뉴스 RAG 분석: {state.get('news_rag_result', '아직 분석 안됨')}

        다음 행동을 결정하세요.
        1. 만약 '모멘텀 분석'과 '뉴스 RAG 분석'이 *모두* 완료되었다면, 이 대화를 끝내고 보고서를 작성할 준비를 하세요. (툴 호출 없이, 최종 요약 메시지만 응답)
        2. 만약 분석이 덜 끝났다면, 필요한 툴(get_sector_etf_momentum, search_sector_news_rag)을 호출하세요.
        3. 7단계를 초과할 것 같으면, 현재까지의 정보로 보고서를 작성할 준비를 하세요. (툴 호출 없이 응답)
        """
        
        # LLM이 툴을 호출할지, 그냥 말할지 결정
        response = llm_with_tools.invoke([HumanMessage(content=prompt)])
        return {"messages": [response]}

    # (Agent 2, 5 등)
    # 실제 툴을 실행하는 노드
    def tool_executor_node(state: AgentState):
        print(f"\n--- [Graph] Node: Tool Executor (Step {state['iteration_count']}) ---")
        
        last_message = state["messages"][-1]
        
        # tool_calls가 없는 경우 (LLM이 툴을 부르지 않음)
        if not last_message.tool_calls:
            print("  > PM이 툴을 호출하지 않았습니다. (아마도 보고서 생성 결정)")
            return {} # 아무것도 안하고 다음 단계로 (라우터가 처리)

        tool_calls = last_message.tool_calls
        tool_messages = []
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
                        
                        # ★★★ 툴 실행 결과를 AgentState의 '상자'에 직접 저장 ★★★
                        if tool_name == "get_sector_etf_momentum":
                            # state["momentum_result"] = result # (이전 코드 - LangGraph 4.0 이상)
                            # LangGraph 3.0 호환성을 위해 state 딕셔너리를 직접 수정하지 않고,
                            # 반환 딕셔너리에 포함시킵니다.
                            pass # (tool_messages에만 추가해도 됨, 하지만 명시적으로 반환하는 것이 더 안전)

                        elif tool_name == "search_sector_news_rag":
                            # state["news_rag_result"] = result # (이전 코드)
                            pass
                            
                        tool_messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
                        found_tool = True
                        break
                    except Exception as e:
                        print(f"  > Tool Execution Error: {e}")
                        tool_messages.append(ToolMessage(content=f"Error: {e}", tool_call_id=call["id"]))
            
            if not found_tool:
                print(f"  > Tool Not Found Error: {tool_name}")
                tool_messages.append(ToolMessage(content=f"Error: Tool '{tool_name}' not found.", tool_call_id=call["id"]))

        return {"messages": tool_messages}

    # (Agent 7: 보고서 생성기 역할)
    def report_generator_node(state: AgentState):
        print(f"\n--- [Graph] Node: Report Generator (Step {state['iteration_count']}) ---")
        
        # 툴 실행 결과는 'messages'에 ToolMessage로 저장되어 있음
        # (더 나은 방법은 state의 momentum_result, news_rag_result를 쓰는 것이지만, 
        # tool_executor_node의 반환값 문제로 일단 messages를 파싱)
        
        # 임시: state['messages']에서 툴 결과 추출 (더 나은 방법은 tool_executor가 state를 직접 업데이트하는 것)
        # 하지만 지금은 툴이 state를 직접 업데이트하지 못할 수 있으므로, 
        # 코디네이터가 툴 결과를 봤다는 가정 하에 마지막 메시지를 기반으로 보고서를 작성
        
        final_prompt_messages = state['messages'] + [HumanMessage(content=f"""
        '{state['sector_name']}' 섹터에 대한 모든 분석이 완료되었습니다.
        지금까지의 대화 기록과 수집된 툴 결과(ToolMessage)를 모두 종합하여,
        3~4문장의 전문적인 투자 분석 요약 보고서를 작성하세요.

        최종 보고서:
        """)]
        
        response = llm.invoke(final_prompt_messages) 
        report_text = response.content
        print(f"  > Final Report Generated: {report_text[:100]}...")
        
        return {"final_report": report_text}

    # --- 4. Graph Edges (엣지/경로) 정의 ---
    
    def router_node(state: AgentState):
        print(f"\n--- [Graph] Node: Router (Step {state['iteration_count']}) ---")
        
        # 1. 7회 루프 제한에 도달했는지 확인
        if state['iteration_count'] >= recursion_limit:
            print("  > 7회 반복 도달. 보고서 생성으로 강제 이동.")
            return "generate_report"
        
        # 2. PM(Coordinator)이 툴을 호출했는지, 아니면 그냥 말했는지 확인
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            print("  > PM이 툴 호출 결정. 툴 실행으로 이동.")
            return "execute_tools"
        else:
            print("  > PM이 툴 호출 안함 (또는 오류). 보고서 생성으로 이동.")
            return "generate_report"

    # --- 5. Graph Workflow (워크플로우) 정의 ---
    workflow = StateGraph(AgentState)
    
    # 5-1. 노드(작업대)들을 공장에 추가
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("report_generator", report_generator_node)
    # ★★★ 버그 수정: "router_node"는 '노드'가 아님!!! ★★★
    # workflow.add_node("router_node", router_node)  # <-- (이전 버그 코드) 삭제!
    
    # 5-2. 엣지(컨베이어 벨트) 연결
    workflow.set_entry_point("coordinator") # "PM 작업대"에서 시작
    
    # ★★★ 버그 수정: "coordinator"에서 "라우터 함수"를 실행 ★★★
    workflow.add_conditional_edges(
        "coordinator", # "PM 작업대"가 끝난 직후에
        router_node,   # "router_node 함수"를 실행해서
        {
            # 만약 "execute_tools"를 반환하면 -> "tool_executor" 작업대로 감
            "execute_tools": "tool_executor",
            # 만약 "generate_report"를 반환하면 -> "report_generator" 작업대로 감
            "generate_report": "report_generator"
        }
    )
    
    # "툴 실행 작업대"가 끝나면 -> 다시 "PM 작업대"로 돌아가서 다음 스텝 결정 (루프)
    workflow.add_edge("tool_executor", "coordinator")
    
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