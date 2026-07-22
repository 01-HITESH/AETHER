from __future__ import annotations

import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from ..config import Settings
from ..repositories.tours import room_label, style_label, tour_to_dict


class ExportService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def report(self, tour: Any) -> Path:
        target = self.settings.exports_dir / f"{tour['id']}-report.html"
        metadata = json.loads(tour["metadata_json"] or "{}")
        requirements = json.loads(tour["requirements_json"] or "{}")
        title = html.escape(tour["title"])
        rows = {
            "Room": room_label(tour["room_type"]),
            "Style": style_label(tour["style"]),
            "Provider": tour["provider"] or "local_demo",
            "Model": tour["model"] or "Not specified",
            "Seed": str(tour["seed"] or 0),
            "Prompt": tour["prompt"] or "Not recorded",
            "Requirements": json.dumps(requirements, ensure_ascii=False),
            "Created": tour["created_at"],
        }
        table = "".join(
            f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
            for label, value in rows.items()
        )
        target.write_text(
            f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title} report</title>
<style>
body{{font-family:Arial,sans-serif;max-width:900px;margin:48px auto;padding:0 24px;color:#202124}}
h1{{font-size:30px}} table{{width:100%;border-collapse:collapse;margin:24px 0}}
th,td{{text-align:left;padding:12px;border-bottom:1px solid #ddd;vertical-align:top}} th{{width:160px}}
img{{width:100%;height:auto;border-radius:6px}} code{{white-space:pre-wrap}}
</style></head><body><h1>{title}</h1>
<p>AETHER generation report with reproducibility metadata.</p>
<table>{table}</table>
<h2>Provider metadata</h2><code>{html.escape(json.dumps(metadata, indent=2, ensure_ascii=False))}</code>
</body></html>""",
            encoding="utf-8",
        )
        return target

    def obj_package(self, tour: Any) -> Path:
        export_dir = self.settings.exports_dir / tour["id"]
        export_dir.mkdir(parents=True, exist_ok=True)
        obj_path = export_dir / "room.obj"
        mtl_path = export_dir / "room.mtl"
        texture_path = Path(tour["redesign_path"] or tour["thumb_path"])
        package_path = self.settings.exports_dir / f"{tour['id']}-obj.zip"
        settings = json.loads(tour["settings_json"] or "{}")
        width = float(settings.get("room_width_m", 5.0))
        depth = float(settings.get("room_depth_m", 4.0))
        height = float(settings.get("room_height_m", 2.8))
        vertices = [
            (0, 0, 0),
            (width, 0, 0),
            (width, 0, depth),
            (0, 0, depth),
            (0, height, 0),
            (width, height, 0),
            (width, height, depth),
            (0, height, depth),
        ]
        faces = [
            (1, 2, 3, 4),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (3, 7, 8, 4),
            (4, 8, 5, 1),
        ]
        lines = [
            "# AETHER room shell OBJ",
            f"# Units: meters; source design: {tour['id']}",
            "mtllib room.mtl",
            "o AETHER_Room",
            *(f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in vertices),
            "vt 0 0",
            "vt 1 0",
            "vt 1 1",
            "vt 0 1",
            "usemtl AETHER_Interior",
            *(f"f {a}/1 {b}/2 {c}/3 {d}/4" for a, b, c, d in faces),
        ]
        obj_path.write_text("\n".join(lines) + "\n", encoding="ascii")
        mtl_path.write_text(
            "newmtl AETHER_Interior\nKa 0.2 0.2 0.2\nKd 0.85 0.85 0.85\n"
            "Ks 0.05 0.05 0.05\nNs 16\nmap_Kd texture.jpg\n",
            encoding="ascii",
        )
        manifest = {
            "format": "Wavefront OBJ package",
            "units": "meters",
            "dimensions": {"width": width, "depth": depth, "height": height},
            "design": tour_to_dict(tour),
        }
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(obj_path, "room.obj")
            archive.write(mtl_path, "room.mtl")
            if texture_path.is_file():
                archive.write(texture_path, "texture.jpg")
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        return package_path


def safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return normalized[:120] or "aether-design"
