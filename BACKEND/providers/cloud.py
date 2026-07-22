from __future__ import annotations

import base64

import httpx

from .base import GenerationProvider, GenerationRequest, GenerationResult, ProviderError


class CloudProvider(GenerationProvider):
    name = "cloud"
    display_name = "Cloud image provider"

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    def generate(self, request, progress, cancelled) -> GenerationResult:
        if not self.endpoint:
            raise ProviderError("AETHER_CLOUD_GENERATION_URL is not configured.")
        self.ensure_not_cancelled(cancelled)
        progress(8, "Preparing cloud inference request")
        payload = {
            "image_base64": base64.b64encode(request.source_path.read_bytes()).decode("ascii"),
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "model": request.model,
            "settings": request.settings,
            "variant_index": request.variant_index,
        }
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        progress(15, "Cloud inference running")
        with httpx.Client(timeout=httpx.Timeout(60.0, read=600.0)) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            self.ensure_not_cancelled(cancelled)
            progress(90, "Downloading cloud result")
            if result.get("image_base64"):
                image_bytes = base64.b64decode(result["image_base64"])
            elif result.get("image_url"):
                image_response = client.get(result["image_url"])
                image_response.raise_for_status()
                image_bytes = image_response.content
            else:
                raise ProviderError("Cloud provider response must include image_base64 or image_url.")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(image_bytes)
        progress(100, "Alternative ready")
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        return GenerationResult(
            image_path=request.output_path,
            metadata={
                **metadata,
                "provider": self.name,
                "request_id": result.get("request_id", ""),
            },
        )
