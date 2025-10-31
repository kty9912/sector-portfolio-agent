import os
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

def get_chat_model() -> BaseChatModel:
    """
    .env 파일의 LLM_PROVIDER 설정에 따라
    적절한 LangChain ChatModel 클라이언트를 반환하는 팩토리 함수입니다.
    
    LangGraph와 모든 에이전트가 이 함수를 호출하여 LLM을 가져옵니다.
    """
    
    # .env에서 어떤 LLM을 쓸지 읽어옵니다. (기본값: openai)
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    print(f"--- [LLM Factory] LLM_PROVIDER='{provider}' ---")

    if provider == "upstage":
        # 1. Upstage (Solar) 모델 반환
        api_key = os.getenv("UPSTAGE_API_KEY")
        if not api_key:
            raise ValueError("Upstage를 사용하려면 UPSTAGE_API_KEY가 .env에 필요합니다.")
            
        print("--- [LLM Factory] Upstage 'solar-pro2' 모델을 로드합니다. ---")
        return ChatOpenAI(
            model="solar-pro2",
            api_key=api_key,
            base_url="https://api.upstage.ai/v1"
        )

    elif provider == "openai":
        # 2. OpenAI (GPT) 모델 반환
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI를 사용하려면 OPENAI_API_KEY가 .env에 필요합니다.")
            
        print("--- [LLM Factory] OpenAI 'gpt-4o-mini' 모델을 로드합니다. ---")
        return ChatOpenAI(
            model="gpt-4o-mini", # gpt-4o, gpt-3.5-turbo 등
            api_key=api_key
            # base_url는 기본값(OpenAI)을 사용합니다.
        )
        
    elif provider == "ollama":
        # 3. Ollama (Local) 모델 반환 (미래 확장용)
        print("--- [LLM Factory] 로컬 'Ollama' 모델을 로드합니다. ---")
        return ChatOllama(
            model="llama3" # 로컬에 설치된 모델명
        )
        
    else:
        raise ValueError(f"알 수 없는 LLM_PROVIDER입니다: {provider}. (upstage, openai, ollama 중 하나를 선택하세요)")
