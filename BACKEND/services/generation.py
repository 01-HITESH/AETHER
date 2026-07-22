from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps

from ..config import Settings
from ..database import Database, utc_now
from ..providers import CloudProvider, ComfyUIProvider, LocalDemoProvider
from ..providers.base import GenerationCancelled, GenerationRequest, ProviderError
from ..repositories.jobs import JobsRepository
from ..repositories.tours import ToursRepository, room_label, style_label, tour_to_dict
from ..services.security import new_id
from ..services.storage import StorageService


class GenerationService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.jobs = JobsRepository(database)
        self.tours = ToursRepository(database, settings)
        self.storage = StorageService(settings, database)
        self.providers = {
            "local_demo": LocalDemoProvider(),
            "comfyui": ComfyUIProvider(settings.comfyui_url, settings.comfyui_workflow_path),
            "cloud": CloudProvider(settings.cloud_generation_url, settings.cloud_generation_api_key),
        }
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._worker_loop, name="aether-generation", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)

    def notify(self) -> None:
        self._wake.set()

    def resolve_provider(self, requested: str) -> str:
        name = (requested or self.settings.generation_provider or "auto").strip().lower()
        aliases = {"local": "local_demo", "demo": "local_demo", "comfy": "comfyui"}
        name = aliases.get(name, name)
        if name == "auto":
            if self.settings.comfyui_workflow_path:
                return "comfyui"
            if self.settings.cloud_generation_url:
                return "cloud"
            return "local_demo"
        if name not in self.providers:
            raise ValueError(f"Unknown generation provider: {name}")
        return name

    def create_job(self, user_id: str, payload: Any) -> dict[str, Any]:
        upload = self.storage.require_upload(payload.uploadId, user_id)
        room_type = normalize_key(payload.roomType, "living_room")
        style = normalize_key(payload.style, "modern")
        provider = self.resolve_provider(payload.provider)
        model = payload.model.strip() or (
            "local-demo-v2" if provider == "local_demo" else self.settings.generation_model
        )
        variant_count = min(4, max(1, int(payload.variantCount or self.settings.generation_variants)))
        seeds = [int(seed) & 0x7FFFFFFF for seed in payload.seeds[:variant_count]]
        while len(seeds) < variant_count:
            seeds.append(random.SystemRandom().randint(1, 2_147_483_647))
        prompt = payload.prompt.strip() or build_prompt(room_type, style, payload.requirements)
        settings = {
            **payload.settings,
            "style": style,
            "room_type": room_type,
            "source_width": int(upload["width"]),
            "source_height": int(upload["height"]),
        }
        row = self.jobs.create(
            {
                "id": new_id("job"),
                "user_id": user_id,
                "upload_id": upload["id"],
                "room_type": room_type,
                "style": style,
                "prompt": prompt,
                "negative_prompt": payload.negativePrompt.strip(),
                "provider": provider,
                "model": model,
                "variant_count": variant_count,
                "settings": settings,
                "requirements": payload.requirements,
                "seeds": seeds,
            }
        )
        self.notify()
        return self.job_to_dict(row)

    def job_to_dict(self, row: Any) -> dict[str, Any]:
        result_ids = json.loads(row["result_tour_ids_json"] or "[]")
        tours = []
        for tour_id in result_ids:
            tour = self.tours.get(tour_id, row["user_id"])
            if tour:
                tours.append(tour_to_dict(tour))
        return {
            "id": row["id"],
            "state": row["state"],
            "progress": int(row["progress"]),
            "upload_id": row["upload_id"],
            "room_type": row["room_type"],
            "style": row["style"],
            "prompt": row["prompt"],
            "negative_prompt": row["negative_prompt"],
            "provider": row["provider"],
            "model": row["model"],
            "variant_count": int(row["variant_count"]),
            "settings": json.loads(row["settings_json"] or "{}"),
            "requirements": json.loads(row["requirements_json"] or "{}"),
            "seeds": json.loads(row["seeds_json"] or "[]"),
            "result_tour_ids": result_ids,
            "alternatives": tours,
            "error": row["error"],
            "attempts": int(row["attempts"]),
            "cancel_requested": bool(row["cancel_requested"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            row = self.jobs.claim_next()
            if not row:
                self._wake.wait(timeout=0.5)
                self._wake.clear()
                continue
            try:
                self._process(row)
            except GenerationCancelled:
                self.jobs.mark_cancelled(row["id"])
            except Exception as exc:
                self.jobs.fail(row["id"], _friendly_error(exc))

    def _process(self, job: Any) -> None:
        job_id = job["id"]
        provider = self.providers[job["provider"]]
        upload = self.storage.require_upload(job["upload_id"], job["user_id"])
        seeds = json.loads(job["seeds_json"] or "[]")
        result_ids = json.loads(job["result_tour_ids_json"] or "[]")
        settings = json.loads(job["settings_json"] or "{}")
        requirements = json.loads(job["requirements_json"] or "{}")
        total = int(job["variant_count"])

        for index in range(len(result_ids), total):
            if self._cancel_requested(job_id):
                raise GenerationCancelled("Generation was cancelled.")
            tour_id = new_id("tour")
            tour_dir = self.settings.tours_dir / tour_id
            redesign_path = tour_dir / "redesign.jpg"
            seed = int(seeds[index])

            def progress(value: int, _message: str) -> None:
                overall = int(((index + max(0, min(100, value)) / 100) / total) * 100)
                self.jobs.update_progress(job_id, overall)
                if self._cancel_requested(job_id):
                    raise GenerationCancelled("Generation was cancelled.")

            result = provider.generate(
                GenerationRequest(
                    source_path=Path(upload["path"]),
                    output_path=redesign_path,
                    prompt=job["prompt"],
                    negative_prompt=job["negative_prompt"],
                    seed=seed,
                    model=job["model"],
                    settings=settings,
                    variant_index=index,
                ),
                progress,
                lambda: self._cancel_requested(job_id),
            )
            image = Image.open(result.image_path).convert("RGB")
            pano_path = tour_dir / "panorama.jpg"
            thumb_path = tour_dir / "thumbnail.jpg"
            make_panorama(image).save(pano_path, "JPEG", quality=91, optimize=True)
            make_thumbnail(image).save(thumb_path, "JPEG", quality=90, optimize=True)
            title = f"{style_label(job['style'])} {room_label(job['room_type'])} {index + 1}"
            metadata = {
                **result.metadata,
                "job_id": job_id,
                "variant_index": index,
                "seed": seed,
                "model": job["model"],
                "provider": job["provider"],
                "prompt": job["prompt"],
                "negative_prompt": job["negative_prompt"],
                "settings": settings,
                "created_at": utc_now(),
            }
            self.tours.create(
                {
                    "id": tour_id,
                    "user_id": job["user_id"],
                    "upload_id": job["upload_id"],
                    "job_id": job_id,
                    "variant_index": index,
                    "title": title,
                    "room_type": job["room_type"],
                    "style": job["style"],
                    "prompt": job["prompt"],
                    "seed": seed,
                    "provider": job["provider"],
                    "model": job["model"],
                    "settings": settings,
                    "requirements": requirements,
                    "metadata": metadata,
                    "redesign_path": str(redesign_path),
                    "pano_path": str(pano_path),
                    "thumb_path": str(thumb_path),
                    "source_path": str(upload["path"]),
                }
            )
            self.jobs.add_result(job_id, tour_id, int(((index + 1) / total) * 100))
        self.jobs.complete(job_id)

    def _cancel_requested(self, job_id: str) -> bool:
        if self._stop.is_set():
            return True
        row = self.jobs.get(job_id)
        return not row or bool(row["cancel_requested"])


def build_prompt(room_type: str, style: str, requirements: dict[str, Any]) -> str:
    details: list[str] = []
    notes = str(requirements.get("notes") or "").strip()
    if notes:
        details.append(notes)
    palette = requirements.get("palette")
    if isinstance(palette, list) and palette:
        details.append("Color palette: " + ", ".join(str(item) for item in palette[:8]))
    budget = requirements.get("budget_level")
    if budget not in (None, ""):
        details.append(f"Budget level: {budget}")
    suffix = ". ".join(details)
    prompt = (
        f"Photorealistic {style_label(style).lower()} redesign of the supplied "
        f"{room_label(room_type).lower()}. Preserve the room geometry, camera position, windows, "
        "doors, and architectural structure. Improve furniture layout, materials, lighting, and styling."
    )
    return f"{prompt} {suffix}".strip()


def normalize_key(value: str, fallback: str) -> str:
    normalized = "_".join(value.strip().lower().replace("-", " ").split())
    return normalized or fallback


def make_thumbnail(image: Image.Image) -> Image.Image:
    return ImageOps.fit(image, (720, 480), method=Image.Resampling.LANCZOS)


def make_panorama(image: Image.Image) -> Image.Image:
    fitted = ImageOps.fit(image, (1536, 768), method=Image.Resampling.LANCZOS)
    mirrored = ImageOps.mirror(fitted)
    pano = Image.new("RGB", (3072, 1536))
    pano.paste(fitted, (0, 384))
    pano.paste(mirrored, (1536, 384))
    top = ImageOps.fit(fitted, (3072, 384), method=Image.Resampling.BICUBIC)
    bottom = ImageEnhance.Brightness(ImageOps.flip(top)).enhance(0.55)
    pano.paste(top, (0, 0))
    pano.paste(bottom, (0, 1152))
    return pano


def job_row_to_dict(row: Any, generation: GenerationService) -> dict[str, Any]:
    return generation.job_to_dict(row)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    if isinstance(exc, ExceptionGroup):
        return "; ".join(str(item) for item in exc.exceptions)
    return f"{exc.__class__.__name__}: {exc}"
