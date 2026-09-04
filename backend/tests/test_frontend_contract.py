from pathlib import Path
import json
import struct


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


def test_github_baseline_wardrobe_is_the_active_runtime() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "wardrobe-v3.js" not in page
    assert "wardrobe-v3.css" not in page
    assert "confirmBatchImport" in page
    assert "analyzeImportText" in page
    assert "github-local-cutout.js" in page
    config = (ROOT / "assets" / "bling-config.js").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8765" in config


def test_github_import_ui_keeps_analysis_and_adds_invisible_local_cutout_adapter() -> None:
    adapter = (ROOT / "assets" / "github-local-cutout.js").read_text(encoding="utf-8")
    assert "analyzeImportText(list[i].name,pic.visual)" in adapter
    assert "'/api/import/photos'" in adapter
    assert "white:garment.white_bg_url" in adapter
    assert "candidateCount:garment.candidate_count" in adapter
    assert "window.BlingCutoutBridge={processAlbumFiles:processAlbumFilesWithCutout,approveDrafts}" in adapter
    assert "event.stopImmediatePropagation()" in adapter
    assert "'/approve'" in adapter


def test_smart_flatlay_review_distinguishes_real_cutout_and_ai_rebuild() -> None:
    runtime = (ROOT / "assets" / "smart-flatlay-v1.js").read_text(encoding="utf-8")
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "smart-flatlay-v1.js" in page
    assert "原图" in runtime
    assert "基础抠图" in runtime
    assert "AI 平铺重建" in runtime
    assert "暖白成品" in runtime
    assert "data-smart-select" in runtime
    assert "detectionBBox" in runtime


def test_local_browser_upload_uses_direct_multipart_route_and_retries_polling() -> None:
    runtime = (ROOT / "assets" / "wardrobe-v3.js").read_text(encoding="utf-8")
    assert "this.request('/api/import/photos'" in runtime
    assert "api.importPhotos(list)" in runtime
    assert "transientErrors >= 6" in runtime


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


def test_dressing_room_reuses_wardrobe_category_sprite() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "#style .outfit-slot .cat-icon" in page
    assert "cat-icon-'+icon" in page
    for icon in ("top", "outer", "pants", "skirt", "shoes", "bag", "accessory", "scarf"):
        assert f"#style .cat-icon-{icon}" in page


def test_local_import_confirmation_saves_image_and_uses_capture_listener() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "function confirmLocalImportDrafts()" in page
    assert "e.target.closest('#confirmBatchImport')" in page
    assert "confirmLocalImportDrafts()},true" in page
    assert "image=d.image||''" in page
    assert "image?'imported':'missing-photo'" in page
    assert "categoryOverviewMode=true" in page


def test_wardrobe_v2_reset_and_photo_elements_block_legacy_sprite_fallback() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "bling-wardrobe-clean-reset-v2" in page
    assert "bling-current-outfit-v2" in page
    assert "bling-tryon-cache-v2" in page
    assert "#itemGrid .itempic," in page
    assert "background-image:none !important" in page
    assert "image.className='wardrobe-photo'" in page
    assert "pic.appendChild(image)" in page
    assert "item&&isStoredWardrobePhoto(item[3])?item[3]:''" in page


def test_season_filter_supports_compound_labels_with_exact_matching() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    for season in ("春", "夏", "秋", "冬", "春夏", "秋冬", "四季"):
        assert f'<option value="{season}">{season}</option>' in page
    assert "(seasons[o.i]||o.x[6]||'四季')===activeSeason" in page
    assert ".includes(activeSeason)" not in page
    assert "let activeSeason='',category='全部'" in page


def test_link_import_normalizes_taobao_and_never_creates_blank_garments() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "function normalizeImportLink(value)" in page
    assert "https://item.taobao.com/item.htm?id=" in page
    assert "if(draft.needImage)failed.push" in page
    assert "这些链接没有生成空白单品" in page
    assert "supplementLinkImages" not in page


def test_import_stays_in_single_imported_category() -> None:
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "importedCategories=[...new Set(importDrafts.map" in page
    assert "categoryOverviewMode=importedCategories.length!==1" in page
    assert "category=importedCategories.length===1?importedCategories[0]:'全部'" in page
    assert "go('wardrobe')" in page


def test_body_viewer_uses_a_real_rigged_glb_and_gradient_bone_scaling() -> None:
    model = ROOT / "assets" / "models" / "generic-rigged-human.glb"
    payload = model.read_bytes()
    assert payload[:4] == b"glTF"
    json_length, json_type = struct.unpack_from("<II", payload, 12)
    assert json_type == 0x4E4F534A
    document = json.loads(payload[20:20 + json_length].decode("utf-8").rstrip("\x00 "))
    assert document.get("skins")
    assert len(document["skins"][0].get("joints", [])) >= 10
    runtime = (ROOT / "assets" / "bling-integration-v2.js").read_text(encoding="utf-8")
    assert "node.isSkinnedMesh&&node.skeleton" in runtime
    assert "node.normalizeSkinWeights()" in runtime
    assert "applyRiggedProfile" in runtime
    assert "mix(thigh,knee,.48)" in runtime
    assert "new THREE.GLTFLoader()" in runtime
