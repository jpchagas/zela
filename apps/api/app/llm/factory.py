from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMClient


@lru_cache
def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "scripted":
        from app.llm.scripted import RuleBasedLLM

        return RuleBasedLLM()

    import anthropic

    from app.llm.anthropic_client import AnthropicLLM

    # The SDK retries 408/409/429/5xx and connection errors itself.
    client = anthropic.Anthropic(timeout=settings.llm_timeout_seconds, max_retries=2)
    return AnthropicLLM(client, model=settings.llm_model, effort=settings.llm_effort)
