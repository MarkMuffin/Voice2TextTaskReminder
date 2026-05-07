from abc import ABC, abstractmethod

from app.domain.schemas import ParsedIntent


class BaseIntentParser(ABC):
    """Abstract LLM intent parser. All providers must implement parse()."""

    @abstractmethod
    async def parse(self, text: str, timezone: str = "Europe/Amsterdam") -> ParsedIntent:
        """Parse user text into structured intent. Never raises — returns unknown on failure."""
        ...


class IntentParseError(Exception):
    pass
