from __future__ import annotations

from pathlib import Path


def test_frontend_demo_mode_is_disabled_by_default():
    source = Path("FRONTEND/shared/aether.js").read_text(encoding="utf-8")
    assert "var DEMO_MODE = true;" in source
    assert "IMAGE_BASE + \"living-room.jpg\"" in source
    assert "IMAGE_BASE + \"room-before.jpg\"" in source
    assert "wireDashboardProjectScroll" in source
    assert "grid.scrollLeft += event.deltaY" in source
    assert "textOf(owner || img)" in source
    assert 'if (this.isDemo() && id === DEMO_TOUR_ID)' in source
    assert '"explore results": "aether_explore_results"' in source


def test_360_view_prioritizes_after_image():
    source = Path("FRONTEND/shared/pano-viewer.js").read_text(encoding="utf-8")
    assert "if (afterUrl)" in source
    assert "Generating 360 view from after image..." in source
