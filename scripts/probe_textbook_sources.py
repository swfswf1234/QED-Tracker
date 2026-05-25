"""Probe additional textbook discovery sources.

This command does not participate in the default one-click downloader. It reports
whether extra official/API-backed sources can provide metadata, manual leads, or
directly downloadable files for a target query.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.utils import setup_console_utf8
from app.tools.open_textbook_sources import (
    GoogleBooksProbe,
    InternetArchiveProbe,
    OpenLibraryProbe,
    manual_search_urls,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="探测更多教材下载/发现来源")
    parser.add_argument("--target", required=True, help="教材名称、作者、版本关键词")
    parser.add_argument("--max-results", type=int, default=5, help="每个来源最多返回结果数")
    return parser.parse_args(argv)


def main():
    setup_console_utf8()
    args = parse_args()
    probes = [
        OpenLibraryProbe(proxy=settings.http_proxy),
        InternetArchiveProbe(proxy=settings.http_proxy),
        GoogleBooksProbe(proxy=settings.http_proxy),
    ]
    try:
        all_results = []
        for probe in probes:
            all_results.extend(probe.search(args.target, max_results=args.max_results))
        all_results.extend(manual_search_urls(args.target))
    finally:
        for probe in probes:
            probe.close()

    print("| Source | Status | Title | Author | Access | URL/Reason |")
    print("| --- | --- | --- | --- | --- | --- |")
    for result in all_results:
        detail = result.url or result.reason
        print(
            f"| {result.source} | {result.status} | {result.title or '-'} | "
            f"{result.author or '-'} | {result.access_type or '-'} | {detail or '-'} |"
        )


if __name__ == "__main__":
    main()
