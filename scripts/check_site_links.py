"""Check internal pages and anchors in the built documentation."""

from __future__ import annotations

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if identifier := values.get("id"):
            self.ids.add(identifier)
        if tag == "a" and (href := values.get("href")):
            self.links.append(href)


def broken_links(site: Path) -> list[str]:
    site = site.resolve()
    pages = {}
    for path in site.rglob("*.html"):
        page = Page()
        page.feed(path.read_text(encoding="utf-8"))
        pages[path] = page
    problems = []
    for path, page in sorted(pages.items()):
        for href in page.links:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc or href.startswith("/"):
                continue
            target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if target.is_dir():
                target /= "index.html"
            where = path.relative_to(site).as_posix()
            if not target.is_file() or not target.is_relative_to(site):
                problems.append(f"{where}: missing page {href}")
            elif (
                parts.fragment
                and target in pages
                and unquote(parts.fragment) not in pages[target].ids
            ):
                problems.append(f"{where}: missing anchor {href}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", type=Path, default=Path("site"))
    args = parser.parse_args()
    if not args.site.is_dir():
        parser.error("build the documentation first")
    problems = broken_links(args.site)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(problems)} broken internal links.")
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(main())
