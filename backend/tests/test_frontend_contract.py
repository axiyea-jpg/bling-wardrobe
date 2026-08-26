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


def test_local_wardrobe_is_primary_while_cloud_runtime_is_paused() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "wardrobe-v3.js" not in page
    assert "wardrobe-v3.css" not in page
    assert "localStorage.setItem('bling-items'" in page


def test_local_wardrobe_keeps_management_filtering_and_analysis_features() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    for feature in (
        'id="manageItems"',
        'id="seasonSelect"',
        'id="pageSize"',
        'id="backCategories"',
        'id="toTop"',
        "analyzeImportText",
        "processAlbumFiles",
        "data-camera=\"1\"",
        "quickLinkImport",
    ):
        assert feature in page


def test_wardrobe_restores_eight_pixel_icon_categories_and_three_import_paths() -> None:
    runtime = (ROOT / "assets" / "wardrobe-v3.js").read_text(encoding="utf-8")
    category_line = next(line for line in runtime.splitlines() if "const CATEGORIES" in line)
    assert category_line.count("'\\u") == 8
    assert "\\u8fde\\u8863\\u88d9" not in category_line
    assert "cat-icon-' + CATEGORY_ICONS" not in runtime  # concatenation is intentionally compact below
    assert "cat-icon-'+CATEGORY_ICONS[category]" in runtime
    assert "data-v3-file-input" in runtime
    assert "data-v3-link-panel" in runtime
    assert "data-v3-camera-input" in runtime
    assert "capture=\"environment\"" in runtime
