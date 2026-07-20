from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .base import CancelCallback, GenerationProvider, GenerationRequest, GenerationResult, ProgressCallback


PALETTES = [
    ((239, 232, 219), (47, 74, 63)),
    ((222, 231, 235), (36, 69, 98)),
    ((238, 224, 211), (111, 67, 53)),
    ((226, 225, 220), (70, 67, 78)),
]


class LocalDemoProvider(GenerationProvider):
    """Offline preview provider. It is deliberately labelled as a demo render."""

    name = "local_demo"

    def generate(
        self,
        request: GenerationRequest,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> GenerationResult:
        if cancelled():
            raise RuntimeError("Generation cancelled.")
        progress(12)
        rng = random.Random(request.seed)
        with Image.open(request.source_path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
        progress(30)
        image = ImageEnhance.Contrast(image).enhance(1.04 + rng.random() * 0.12)
        image = ImageEnhance.Color(image).enhance(0.82 + rng.random() * 0.25)
        base, accent = PALETTES[request.variant_index % len(PALETTES)]
        tint = Image.new("RGB", image.size, base)
        image = Image.blend(image, tint, 0.10 + request.variant_index * 0.018)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.4, percent=85, threshold=3))
        progress(58)
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        floor_y = int(height * 0.68)
        draw.polygon(
            [(0, floor_y), (width, floor_y), (width, height), (0, height)],
            fill=(*base, 32),
        )
        rug_w, rug_h = int(width * 0.42), int(height * 0.13)
        rug_x = (width - rug_w) // 2 + rng.randint(-max(1, width // 30), max(1, width // 30))
        draw.rounded_rectangle(
            (rug_x, int(height * 0.77), rug_x + rug_w, int(height * 0.77) + rug_h),
            radius=max(4, height // 60),
            fill=(*accent, 42),
            outline=(*accent, 95),
            width=max(2, width // 500),
        )
        if cancelled():
            raise RuntimeError("Generation cancelled.")
        progress(82)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.output_path, "JPEG", quality=92, optimize=True)
        progress(100)
        return GenerationResult(
            image_path=request.output_path,
            metadata={
                "provider": self.name,
                "model": request.model,
                "seed": request.seed,
                "settings": request.settings,
                "demo": True,
                "note": "Offline deterministic preview; configure ComfyUI or Cloud for AI generation.",
            },
        )

