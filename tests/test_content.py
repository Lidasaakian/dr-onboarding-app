"""Saved edits of built-in paths (spec content-management)."""


def test_saved_agentic_edit_uses_current_page_code(app_module):
    old_page = app_module.DEPLOYED_AGENTIC.replace("DROnb.builtinEditing", "oldScriptWithoutTheButton")
    edited = app_module.splice_main(old_page, "<p>Edited by an admin</p>")
    app_module.docs.put("content-agentic", {"html": edited, "publishedAt": 1, "publishedBy": "Admin", "file": "edited in the app"})
    try:
        html, src = app_module._live_agentic()
        assert src["kind"] == "uploaded"
        assert "Edited by an admin" in html
        assert "DROnb.builtinEditing" in html and "oldScriptWithoutTheButton" not in html
    finally:
        app_module.docs.put("content-agentic", {"reverted": True, "publishedAt": 2, "publishedBy": "Admin"})


def test_content_status_reports_saved_edits(client, app_module):
    app_module.docs.put("content-agentic", {"html": app_module.splice_main(app_module.DEPLOYED_AGENTIC, "<p>x</p>"),
                                            "publishedAt": 1, "publishedBy": "Admin"})
    app_module.activate_content()
    try:
        kinds = {p["id"]: p["source"]["kind"] for p in client.get("/api/admin/content").json()["paths"]}
        assert kinds["agentic"] == "uploaded"
        assert client.post("/api/admin/content/agentic/revert").status_code == 200
        kinds = {p["id"]: p["source"]["kind"] for p in client.get("/api/admin/content").json()["paths"]}
        assert kinds["agentic"] == "deployed"
    finally:
        app_module.docs.put("content-agentic", {"reverted": True, "publishedAt": 2, "publishedBy": "Admin"})
        app_module.activate_content()
