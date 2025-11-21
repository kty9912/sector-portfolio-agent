import pytest
from core.llm_clients import get_chat_model, AVAILABLE_MODELS

def test_available_models():
    assert isinstance(AVAILABLE_MODELS, list)
    assert len(AVAILABLE_MODELS) > 0

@pytest.mark.skip(reason="API 키 필요 및 외부 호출 환경 의존")
def test_get_chat_model_valid():
    model_name = AVAILABLE_MODELS[0]
    model = get_chat_model(model_name)
    assert model is not None
