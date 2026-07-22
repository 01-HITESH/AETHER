from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .base import GenerationProvider, GenerationRequest, GenerationResult, ProviderError


class ComfyUIProvider(GenerationProvider):
    name = "comfyui"
    display_name = "ComfyUI"

    def __init__(self, base_url: str, workflow_path: str):
        self.base_url = base_url.rstrip("/")
        self.workflow_path = Path(workflow_path).expanduser() if workflow_path else None

    def generate(self, request, progress, cancelled) -> GenerationResult:
        if not self.workflow_path or not self.workflow_path.is_file():
            raise ProviderError(
                "COMFYUI_WORKFLOW_PATH must point to an API-format ComfyUI workflow JSON file."
            )
        self.ensure_not_cancelled(cancelled)
        progress(5, "Uploading source image to ComfyUI")
        with httpx.Client(timeout=httpx.Timeout(60.0, read=120.0)) as client:
            with request.source_path.open("rb") as handle:
                upload = client.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (request.source_path.name, handle, "image/jpeg")},
                    data={"overwrite": "true"},
                )
            upload.raise_for_status()
            uploaded_name = upload.json().get("name") or request.source_path.name

            workflow = json.loads(self.workflow_path.read_text(encoding="utf-8"))
            replacements = {
                "${PROMPT}": request.prompt,
                "${NEGATIVE_PROMPT}": request.negative_prompt,
                "${SEED}": request.seed,
                "${MODEL}": request.model,
                "${INPUT_IMAGE}": uploaded_name,
            }
            workflow = _replace_values(workflow, replacements)
            progress(12, "Submitting ComfyUI workflow")
            response = client.post(f"{self.base_url}/prompt", json={"prompt": workflow})
            response.raise_for_status()
            prompt_id = response.json().get("prompt_id")
            if not prompt_id:
                raise ProviderError("ComfyUI did not return a prompt_id.")

            started = time.monotonic()
            while True:
                self.ensure_not_cancelled(cancelled)
                history_response = client.get(f"{self.base_url}/history/{prompt_id}")
                history_response.raise_for_status()
                history = history_response.json().get(prompt_id)
                if history:
                    output = _first_image(history)
                    if output:
                        progress(92, "Downloading ComfyUI result")
                        image_response = client.get(
                            f"{self.base_url}/view",
                            params={
                                "filename": output["filename"],
                                "subfolder": output.get("subfolder", ""),
                                "type": output.get("type", "output"),
                            },
                        )
                        image_response.raise_for_status()
                        request.output_path.parent.mkdir(parents=True, exist_ok=True)
                        request.output_path.write_bytes(image_response.content)
                        progress(100, "Alternative ready")
                        return GenerationResult(
                            image_path=request.output_path,
                            metadata={
                                "provider": self.name,
                                "prompt_id": prompt_id,
                                "output": output,
                                "elapsed_seconds": round(time.monotonic() - started, 2),
                            },
                        )
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise ProviderError(f"ComfyUI workflow failed: {status}")
                elapsed = time.monotonic() - started
                progress(min(88, 15 + int(elapsed / 2)), "ComfyUI inference running")
                time.sleep(1)


def _replace_values(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_values(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_values(item, replacements) for item in value]
    if isinstance(value, str):
        if value in replacements:
            return replacements[value]
        result = value
        for placeholder, replacement in replacements.items():
            result = result.replace(placeholder, str(replacement))
        return result
    return value


def _first_image(history: dict[str, Any]) -> dict[str, Any] | None:
    for node in (history.get("outputs") or {}).values():
        images = node.get("images") or []
        if images:
            return images[0]
    return None
