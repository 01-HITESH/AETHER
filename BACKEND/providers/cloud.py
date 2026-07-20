from __future__ import annotations

import base64
import json
import urllib.request

from .base import CancelCallback, GenerationProvider, GenerationRequest, GenerationResult, ProgressCallback


class CloudProvider(GenerationProvider):
    """Generic JSON image-to-image adapter for a configured HTTPS endpoint."""

    name = "cloud"

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    def generate(
        self,
        request: GenerationRequest,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> GenerationResult:
        if not self.endpoint or not self.api_key:
            raise RuntimeError("Cloud generation requires AETHER_CLOUD_GENERATION_URL and API key.")
        if not self.endpoint.lower().startswith("https://"):
            raise RuntimeError("Cloud generation endpoint must use HTTPS.")
        progress(8)
        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "model": request.model,
            "settings": request.settings,
            "image": base64.b64encode(request.source_path.read_bytes()).decode("ascii"),
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        if cancelled():
            raise RuntimeError("Generation cancelled.")
        progress(20)
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read())
        encoded = result.get("image") or result.get("image_base64")
        if not encoded:
            raise RuntimeError("Cloud provider response did not contain an image.")
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(base64.b64decode(encoded))
        progress(100)
        return GenerationResult(request.output_path, {"provider": self.name, **result.get("metadata", {})})

