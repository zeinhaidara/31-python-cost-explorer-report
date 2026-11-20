"""Command line entry point: python -m cost_report --tag team --top 5"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from cost_report.explorer import WeekWindow, fetch_weekly_costs
from cost_report.report import build_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Weekly AWS Cost Explorer report in Markdown.")
    p.add_argument(
        "--end",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="exclusive end date YYYY-MM-DD (default: today, UTC)",
    )
    p.add_argument("--tag", help="cost allocation tag key to group by, e.g. team")
    p.add_argument("--top", type=int, default=5, help="rows per table (default 5)")
    p.add_argument("--output", type=Path, help="write Markdown here instead of stdout")
    args = p.parse_args(argv)
    if args.top < 1:
        p.error("--top must be at least 1")
    return args


def run(client, args: argparse.Namespace) -> str:
    window = WeekWindow(end=args.end)
    by_service = fetch_weekly_costs(client, window)
    by_tag = fetch_weekly_costs(client, window, tag_key=args.tag) if args.tag else None
    return build_report(window, by_service, top_n=args.top, tag_key=args.tag, by_tag=by_tag)


def main(argv: list[str] | None = None, client=None) -> int:
    args = parse_args(argv)
    if client is None:
        import boto3

        # Cost Explorer is served from us-east-1 only.
        client = boto3.client("ce", region_name="us-east-1")
    try:
        markdown = run(client, args)
    except Exception as exc:
        # Report and exit non-zero; never write a partial report.
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    return 0
