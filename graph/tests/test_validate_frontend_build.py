from pathlib import Path

from scripts.validate_frontend_build import find_missing_assets


def test_frontend_build_asset_references_exist(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<link rel="icon" href="/favicon.svg">'
        '<script src="/assets/app.js"></script>'
        '<img src="data:image/svg+xml,inline">',
        encoding="utf-8",
    )

    assert find_missing_assets(tmp_path) == []


def test_frontend_build_reports_missing_and_escaping_assets(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<script src="/assets/missing.js"></script>'
        '<link href="/../outside.css">',
        encoding="utf-8",
    )

    assert find_missing_assets(tmp_path) == ["../outside.css", "assets/missing.js"]
