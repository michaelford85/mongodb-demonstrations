"""LLM provider selection for Call Policy Agent."""

from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr
from langchain_core.language_models import BaseChatModel

MODEL = "claude-sonnet-5"


def build_llm(temperature: float = 0) -> BaseChatModel:
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is missing; add it to .env or project secrets")
    return ChatAnthropic(
        model_name=MODEL,
        api_key=SecretStr(api_key),
    )
