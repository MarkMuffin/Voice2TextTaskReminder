import logging
from collections.abc import Sequence

from app.domain.schemas import ParsedIntent
from app.providers.llm.base import BaseIntentParser
from app.providers.llm.openai_compatible import _safe_fallback, is_safe_fallback

logger = logging.getLogger(__name__)

_MAX_ERROR_CHARS = 500


class FallbackIntentParser(BaseIntentParser):
    """Try intent parsers in order, returning the first usable parsed intent."""

    def __init__(self, providers: Sequence[tuple[str, BaseIntentParser]]) -> None:
        if not providers:
            raise ValueError("FallbackIntentParser requires at least one provider")
        self.providers = list(providers)

    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        failures: list[str] = []

        for name, provider in self.providers:
            try:
                intent = await provider.parse(text, timezone)
            except Exception as exc:
                failures.append(f"{name}: {str(exc)[:_MAX_ERROR_CHARS]}")
                logger.warning("LLM provider %s failed, trying next provider: %s", name, exc)
                continue

            if is_safe_fallback(intent):
                failures.append(f"{name}: returned safe fallback")
                logger.warning("LLM provider %s returned safe fallback, trying next provider", name)
                continue

            return intent

        logger.warning("All LLM providers failed: %s", "; ".join(failures))
        return _safe_fallback()
