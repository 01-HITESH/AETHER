from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


ProgressCallback = Callable[[int, str], None]
CancellationCheck = Callable[[], bool]


class ProviderError(RuntimeError):
    pass


class GenerationCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class GenerationRequest:
    source_path: Path
    output_path: Path
    prompt: str
    negative_prompt: str
    seed: int
    model: str
    settings: dict[str, Any] = field(default_factory=dict)
    variant_index: int = 0


@dataclass(frozen=True)
class GenerationResult:
    image_path: Path
    metadata: dict[str, Any]


class GenerationProvider(ABC):
    name: str
    display_name: str

    @abstractmethod
    def generate(
        self,
        request: GenerationRequest,
        progress: ProgressCallback,
        cancelled: CancellationCheck,
    ) -> GenerationResult:
        raise NotImplementedError

    @staticmethod
    def ensure_not_cancelled(cancelled: CancellationCheck) -> None:
        if cancelled():
            raise GenerationCancelled("Generation was cancelled.")
