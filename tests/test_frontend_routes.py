from __future__ import annotations


def test_frontend_page_aliases_resolve(client):
    aliases = {
        "aether_authentication": "authentication.html",
        "aether_dashboard": "dashboard.html",
        "aether_upload_room": "uploadroom.html",
        "aether_style_selection": "style selection.html",
        "aether_describe_requirements": "describe requirements.html",
        "aether_saved_designs": "designs saved.html",
        "aether_explore_results": "explore results.html",
        "aether_generating_design": "generating design.html",
        "aether_project_details": "project details.html",
        "aether_profile_settings": "profilesettings.html",
        "aether_interactive_3d_walkthrough": "interactive 3d-walkthrough.html",
        "aether_ai_interior_design_hero_2": "homepage(hero section).html",
    }

    for alias, _target in aliases.items():
        response = client.get(f"/app/pages/{alias}.html")
        assert response.status_code == 200, f"Missing alias: {alias}"
        assert str(response.url).endswith(f"/{alias}.html")
