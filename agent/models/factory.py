from __future__ import annotations

from apps.api.settings import ModelSettings
from agent.models.base import ModelAdapter
from agent.models.openai_function_calling_adapter import OpenAIFunctionCallingAdapter
from agent.models.rule_based_adapter import RuleBasedModelAdapter


def build_model_adapter(settings: ModelSettings) -> ModelAdapter:
    provider = settings.provider.strip().lower()
    if provider in {"", "rule", "rule_based", "deterministic"}:
        return RuleBasedModelAdapter()

    if provider in {"openai", "openai_function_calling"}:
        if not settings.api_key:
            raise RuntimeError(
                "MODEL_PROVIDER=openai requires OPENAI_API_KEY. "
                "Use MODEL_PROVIDER=rule_based for local deterministic mode."
            )
        return OpenAIFunctionCallingAdapter(
            api_key=settings.api_key,
            model=settings.model,
            base_url=settings.base_url,
            temperature=settings.temperature,
        )

    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.provider}")
