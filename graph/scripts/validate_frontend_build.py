"""Validate that root-relative assets referenced by the built frontend exist."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class _AssetReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in {"href", "src"} or not value or not value.startswith("/"):
                continue
            if value.startswith("//"):
                continue
            path = unquote(urlsplit(value).path).lstrip("/")
            if path:
                self.references.add(path)


def find_missing_assets(dist_dir: Path) -> list[str]:
    index_path = dist_dir / "index.html"
    if not index_path.is_file():
        return ["index.html"]

    parser = _AssetReferenceParser()
    parser.feed(index_path.read_text(encoding="utf-8"))
    root = dist_dir.resolve()
    missing: list[str] = []
    for reference in sorted(parser.references):
        target = (dist_dir / reference).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            missing.append(reference)
            continue
        if not target.is_file():
            missing.append(reference)
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        type=Path,
        default=Path("application/frontend/dist"),
        help="Vite build output directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = find_missing_assets(args.dist)
    if missing:
        print("[FAIL] Frontend build has missing asset references:")
        for reference in missing:
            print(f"  - /{reference}")
        return 1
    print(f"[OK] Frontend build asset references are valid: {args.dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
