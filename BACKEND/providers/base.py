from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[int], None]
CancelCallback = Callable[[], bool]


@dataclass
class GenerationRequest:
    source_path: Path
    output_path: Path
    prompt: str
    negative_prompt: str
    seed: int
    model: str
    settings: dict[str, Any] = field(default_factory=dict)
    variant_index: int = 0


@dataclass
class GenerationResult:
    image_path: Path
    metadata: dict[str, Any]


class GenerationProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(
        self,
        request: GenerationRequest,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> GenerationResult:
        raise NotImplementedError

