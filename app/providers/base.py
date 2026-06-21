"""Provider abstraction.

The whole point of a gateway is that the rest of the app never talks to a
vendor SDK directly — it talks to this interface. Swapping MiniMax for a
self-hosted vLLM endpoint (Part 7) later means writing one new subclass and
changing one config value. No router or business code changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from app.schemas import Message


@dataclass
class CompletionResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult:
        ...

    @abstractmethod
    async def aclose(self) -> None:
        ...
