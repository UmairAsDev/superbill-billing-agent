from langchain_openai import ChatOpenAI
from config.config import settings


def get_openai_llm() -> ChatOpenAI:
    """
    Factory function that returns the configured OpenAI LLM instance.
    Model, temperature, and seed are driven by settings / .env.
    Streaming is intentionally disabled — callers use ainvoke() without a
    streaming sink, so enabling it only adds latency overhead.
    """
    from pydantic import SecretStr

    return ChatOpenAI(
        api_key=SecretStr(settings.OPENAI_API_KEY),
        model=settings.MODEL_NAME,
        temperature=settings.TEMPERATURE,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    )
