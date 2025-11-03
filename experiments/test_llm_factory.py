# python -m experiments.test_llm_factory
# 스크립트가 아닌 모듈로 실행하기 위해 위 명령어를 사용해야 함

import os
from dotenv import load_dotenv

# 중요: .env 파일을 먼저 로드해야 합니다!
print("'.env' 파일 로드 중...")
load_dotenv()

# .env 로드 후, 팩토리 함수를 임포트합니다.
from core.llm_clients import get_chat_model

def run_llm_test():
    """
    .env 파일의 LLM_PROVIDER 설정에 따라
    선택된 LLM이 실제로 작동하는지 테스트합니다.
    """
    try:
        # 1. 팩토리에서 LLM 가져오기
        #    (이 함수는 .env를 읽고 Upstage 또는 OpenAI 모델을 반환합니다)
        chat_model = get_chat_model()

        # 2. LLM에 테스트 질문하기 (LangChain 방식)
        print("\n--- [Test] LLM에 질문을 전송합니다... ---")
        response = chat_model.invoke("안녕하세요! 당신은 어느 회사에서 만들어진 모델인가요?")
        
        print("\n--- [Test] LLM 응답: ---")
        print(response.content)

        # 3. (참고) Upstage 공식 문서의 'stream=True' 방식 테스트
        if os.getenv("LLM_PROVIDER") == "upstage":
            print("\n--- [Test] Upstage (Stream=True) 방식 테스트: ---")
            stream = chat_model.stream("1부터 5까지 숫자를 세어주세요.")
            for chunk in stream:
                if chunk.content:
                    print(chunk.content, end="", flush=True)
            print("\n--- [Test] 스트리밍 완료 ---")

    except Exception as e:
        print(f"\n[에러 발생] 테스트 실패: {e}")
        print("(.env 파일에 API 키와 LLM_PROVIDER가 올바르게 설정되었는지 확인하세요.)")


if __name__ == "__main__":
    run_llm_test()
