from typing import Type, TypeVar, Protocol
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class LLMProvider(Protocol):
    async def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        """
        Generates structured data matching the provided Pydantic schema
        based on the given prompt.
        """
        ...
