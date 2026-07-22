from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .base import GenerationProvider, GenerationRequest, GenerationResult


STYLE_TINTS = {
    "modern": (226, 226, 218),
    "minimalist": (242, 239, 229),
    "luxury": (194, 164, 112),
    "scandinavian": (229, 223, 205),
    "japanese_zen": (177, 185, 155),
    "industrial": (112, 119, 124),
    "contemporary": (154, 178, 186),
    "traditional": (178, 139, 105),
    "bohemian": (188, 116, 88),
    "classical": (207, 190, 151),
}


class LocalDemoProvider(GenerationProvider):
    name = "local_demo"
    display_name = "Local demo renderer"

    def generate(self, request, progress, cancelled) -> GenerationResult:
        self.ensure_not_cancelled(cancelled)
        progress(10, "Reading source image")
        source = Image.open(request.source_path)
        source = ImageOps.exif_transpose(source).convert("RGB")
        source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        rng = random.Random(request.seed)
        style = str(request.settings.get("style", "modern"))
        tint = STYLE_TINTS.get(style, STYLE_TINTS["modern"])

        progress(30, "Applying style and lighting")
        image = ImageEnhance.Color(source).enhance(0.82 + rng.random() * 0.28)
        image = ImageEnhance.Contrast(image).enhance(1.03 + rng.random() * 0.12)
        image = ImageEnhance.Brightness(image).enhance(1.02 + rng.random() * 0.08)
        overlay = Image.new("RGB", image.size, tint)
        image = Image.blend(image, overlay, 0.08 + rng.random() * 0.08)

        self.ensure_not_cancelled(cancelled)
        progress(55, "Composing interior concept")
        canvas = image.convert("RGBA")
        draw = ImageDraw.Draw(canvas, "RGBA")
        width, height = canvas.size
        floor_top = int(height * (0.60 + rng.uniform(-0.03, 0.03)))
        draw.polygon(
            [(0, floor_top), (width, floor_top), (width, height), (0, height)],
            fill=(45, 39, 34, 24),
        )
        accent = (*tint, 205)
        furniture_y = int(height * 0.67)
        furniture_w = int(width * (0.42 + rng.random() * 0.12))
        furniture_h = int(height * (0.14 + rng.random() * 0.05))
        furniture_x = int((width - furniture_w) * (0.35 + rng.random() * 0.3))
        radius = max(8, int(min(width, height) * 0.018))
        draw.rounded_rectangle(
            (furniture_x, furniture_y, furniture_x + furniture_w, furniture_y + furniture_h),
            radius=radius,
            fill=(38, 42, 44, 185),
            outline=accent,
            width=max(2, width // 500),
        )
        for offset in (0.13, 0.72):
            x = int(furniture_x + furniture_w * offset)
            draw.rectangle(
                (x, furniture_y + furniture_h, x + max(3, width // 180), height * 0.87),
                fill=(30, 29, 27, 180),
            )
        rug_w = int(width * 0.55)
        rug_h = int(height * 0.12)
        rug_x = (width - rug_w) // 2
        rug_y = int(height * 0.82)
        draw.ellipse(
            (rug_x, rug_y, rug_x + rug_w, rug_y + rug_h),
            fill=(*tint, 88),
            outline=(*tint, 135),
            width=max(2, width // 600),
        )

        self.ensure_not_cancelled(cancelled)
        progress(80, "Refining generated alternative")
        image = canvas.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3))
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(request.output_path, "JPEG", quality=94, optimize=True, progressive=True)
        progress(100, "Alternative ready")
        return GenerationResult(
            image_path=request.output_path,
            metadata={
                "provider": self.name,
                "renderer": "pillow-local-demo-v2",
                "seed": request.seed,
                "source_size": [source.width, source.height],
                "output_size": [image.width, image.height],
                "note": "Local demo provider; configure ComfyUI or a cloud endpoint for model inference.",
            },
        )
