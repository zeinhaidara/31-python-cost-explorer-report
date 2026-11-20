"""Hand-written stand-in for the boto3 Cost Explorer client."""

from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeCostExplorer:
    """Serves canned pages per GroupBy key and records every request.

    `pages` maps "SERVICE" or a tag key to a list of response pages. Each
    page after the first is only served for the token the previous page gave.
    """

    def __init__(self, pages: dict[str, list[dict]] | None = None, error: Exception | None = None):
        self.pages = pages or {}
        self.error = error
        self.calls: list[dict] = []

    def get_cost_and_usage(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if self.error is not None:
            raise self.error
        key = kwargs["GroupBy"][0]["Key"]
        pages = self.pages[key]
        token = kwargs.get("NextPageToken")
        if token is None:
            return copy.deepcopy(pages[0])
        for i, page in enumerate(pages[:-1]):
            if page.get("NextPageToken") == token:
                return copy.deepcopy(pages[i + 1])
        raise AssertionError(f"unexpected NextPageToken {token!r}")
