from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_v3_runtime_never_uses_legacy_sprite_or_base64_storage() -> None:
    runtime = (ROOT / "assets" / "wardrobe-v3.js").read_text(encoding="utf-8")
    assert "removeProperty('--items-img')" in runtime
    assert "var(--items-img)" not in runtime
    assert "data:image" not in runtime
    assert "seedWardrobe" not in runtime
    for legacy_class in ("'p1'", "'p2'", "'p3'", "'p4'", "'p5'", "'p6'", "'p7'", "'p8'"):
        assert legacy_class not in runtime
    assert "thumbnail_url" in runtime
    assert "modeled_preview_url" in runtime


def test_v3_runtime_uses_stable_ids_and_debounced_tryon() -> None:
    runtime = (ROOT / "assets" / "wardrobe-v3.js").read_text(encoding="utf-8")
    assert "garment_ids" in runtime
    assert "new Set(garmentIds)" in runtime
    assert "setTimeout" in runtime and "800" in runtime
    assert "body_model_id" in runtime


def test_v3_runtime_loads_after_legacy_bundle() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert page.rfind("wardrobe-v3.js") > page.rfind("</script>") - 3000
