from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .base import CancelCallback, GenerationProvider, GenerationRequest, GenerationResult, ProgressCallback


class ComfyUIProvider(GenerationProvider):
    name = "comfyui"

    def __init__(self, base_url: str, workflow_path: str):
        self.base_url = base_url.rstrip("/")
        self.workflow_path = workflow_path

    def _json(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())

    def generate(
        self,
        request: GenerationRequest,
        progress: ProgressCallback,
        cancelled: CancelCallback,
    ) -> GenerationResult:
        workflow_file = Path(self.workflow_path)
        if not workflow_file.is_file():
            raise RuntimeError("AETHER_COMFYUI_WORKFLOW must point to a valid API workflow JSON file.")
        workflow = json.loads(workflow_file.read_text(encoding="utf-8"))
        serialized = json.dumps(workflow)
        serialized = serialized.replace("{{PROMPT}}", request.prompt)
        serialized = serialized.replace("{{NEGATIVE_PROMPT}}", request.negative_prompt)
        serialized = serialized.replace("{{SEED}}", str(request.seed))
        workflow = json.loads(serialized)
        client_id = uuid.uuid4().hex
        queued = self._json("/prompt", {"prompt": workflow, "client_id": client_id})
        prompt_id = queued.get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt id.")
        progress(10)
        for tick in range(240):
            if cancelled():
                try:
                    self._json("/interrupt", {})
                finally:
                    raise RuntimeError("Generation cancelled.")
            history = self._json("/history/" + urllib.parse.quote(prompt_id))
            item = history.get(prompt_id)
            if item:
                outputs = item.get("outputs", {})
                for output in outputs.values():
                    images = output.get("images", [])
                    if not images:
                        continue
                    image = images[0]
                    query = urllib.parse.urlencode(
                        {"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
                    )
                    with urllib.request.urlopen(self.base_url + "/view?" + query, timeout=60) as response:
                        request.output_path.parent.mkdir(parents=True, exist_ok=True)
                        request.output_path.write_bytes(response.read())
                    progress(100)
                    return GenerationResult(request.output_path, {"provider": self.name, "promptId": prompt_id})
                status = item.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError("ComfyUI reported a generation error.")
            progress(min(92, 10 + tick // 3))
            time.sleep(0.5)
        raise RuntimeError("ComfyUI generation timed out.")

