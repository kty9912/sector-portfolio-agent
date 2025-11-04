import os
from langchain_core.chat_models import BaseChatModel

# --- .env 파일에서 LLM 공급자별 API 키와 모델 이름을 "미리" 읽어옵니다. ---
# (main.py에서 load_dotenv()를 실행한 *이후*에 이 파일이 임포트되어야 합니다.)

# 1. Upstage
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
UPSTAGE_MODEL_NAME = os.getenv("LLM_PROVIDER_UPSTAGE_MODEL", "solar-pro2") 

# 2. OpenAI (새로 추가!)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("LLM_PROVIDER_OPENAI_MODEL", "gpt-4o-mini")

# 3. Google Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.getenv("LLM_PROVIDER_GEMINI_MODEL", "gemini-1.5-pro")

# 4. Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL_NAME = os.getenv("LLM_PROVIDER_GROQ_MODEL", "llama3-8b-8192")


# --- 사용 가능한 모델의 "전체 목록" ---
# (API 키가 없어도, FastAPI가 enum을 생성할 수 있도록 이름을 정의합니다.)
# .env 파일에 API 키가 "있는" 모델만 동적으로 추가합니다.
AVAILABLE_MODELS = []
if UPSTAGE_API_KEY:
    AVAILABLE_MODELS.append(UPSTAGE_MODEL_NAME)
if OPENAI_API_KEY:
    AVAILABLE_MODELS.append(OPENAI_MODEL_NAME)
if GOOGLE_API_KEY:
    AVAILABLE_MODELS.append(GEMINI_MODEL_NAME)
if GROQ_API_KEY:
    AVAILABLE_MODELS.append(GROQ_MODEL_NAME)

# 만약 아무 키도 없다면, 임시 값을 넣어 FastAPI 에러를 방지합니다.
if not AVAILABLE_MODELS:
    AVAILABLE_MODELS = ["No Models Loaded (Check .env file)"]


def get_chat_model(model_name: str) -> BaseChatModel:
    """
    LLM 팩토리: .env 파일과 모델 이름을 기반으로
    올바른 LLM 클라이언트(Upstage, OpenAI, Gemini 등)를 반환합니다.
    """
    
    # --- 각 모델에 대한 클라이언트 생성 로직 ---
    # (API 키가 있는 모델만 실제로 생성됩니다.)

    if model_name == UPSTAGE_MODEL_NAME and UPSTAGE_API_KEY:
        # Upstage는 OpenAI와 API 호환이 되므로 ChatOpenAI를 사용합니다.
        from langchain_openai import ChatOpenAI
        print(f"--- [LLM Factory] Upstage '{model_name}' 모델을 로드합니다. ---")
        return ChatOpenAI(
            model=model_name,
            api_key=UPSTAGE_API_KEY,
            base_url="https://api.upstage.ai/v1"
        )
    
    elif model_name == OPENAI_MODEL_NAME and OPENAI_API_KEY:
        # OpenAI (새로 추가!)
        from langchain_openai import ChatOpenAI
        print(f"--- [LLM Factory] OpenAI '{model_name}' 모델을 로드합니다. ---")
        return ChatOpenAI(
            model=model_name,
            api_key=OPENAI_API_KEY
        )
        
    elif model_name == GEMINI_MODEL_NAME and GOOGLE_API_KEY:
        # Google Gemini
        from langchain_google_genai import ChatGoogleGenerativeAI
        print(f"--- [LLM Factory] Google '{model_name}' 모델을 로드합니다. ---")
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=GOOGLE_API_KEY
        )
        
    elif model_name == GROQ_MODEL_NAME and GROQ_API_KEY:
        # Groq
        from langchain_groq import ChatGroq
        print(f"--- [LLM Factory] Groq '{model_name}' 모델을 로드합니다. ---")
        return ChatGroq(
            model_name=model_name,
            groq_api_key=GROQ_API_KEY
        )
    
    else:
        # 이 에러는 get_chat_model이 호출되었지만, 
        # API 키가 .env에 없어서 모델을 로드할 수 없을 때 발생합니다.
        raise ValueError(f"'{model_name}'에 대한 API 키가 .env 파일에 없거나, 모델을 지원하지 않습니다.")

