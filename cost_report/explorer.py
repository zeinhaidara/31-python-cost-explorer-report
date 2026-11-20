"""Read two weeks of spend from AWS Cost Explorer, grouped by service or tag."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

METRIC = "UnblendedCost"
UNTAGGED = "(untagged)"


class CostDataError(Exception):
    """Cost Explorer answered, but with data we can't build a report from."""


@dataclass(frozen=True)
class WeekWindow:
    """Two back-to-back 7-day windows. `end` is exclusive, like Cost Explorer."""

    end: date

    @property
    def current_start(self) -> date:
        return self.end - timedelta(days=7)

    @property
    def previous_start(self) -> date:
        return self.end - timedelta(days=14)


@dataclass
class WeeklyCosts:
    current: dict[str, Decimal]
    previous: dict[str, Decimal]


def fetch_weekly_costs(client, window: WeekWindow, tag_key: str | None = None) -> WeeklyCosts:
    """Group cost by SERVICE, or by `tag_key` when given."""
    if tag_key is not None and not tag_key.strip():
        raise ValueError("tag_key must not be blank")
    group_by = (
        {"Type": "TAG", "Key": tag_key} if tag_key else {"Type": "DIMENSION", "Key": "SERVICE"}
    )
    request = {
        "TimePeriod": {
            "Start": window.previous_start.isoformat(),
            "End": window.end.isoformat(),
        },
        "Granularity": "DAILY",
        "Metrics": [METRIC],
        "GroupBy": [group_by],
    }

    current: dict[str, Decimal] = {}
    previous: dict[str, Decimal] = {}
    saw_group = False

    for result in _results_by_time(client, request):
        day = date.fromisoformat(result["TimePeriod"]["Start"])
        if window.current_start <= day < window.end:
            bucket = current
        elif window.previous_start <= day < window.current_start:
            bucket = previous
        else:
            raise CostDataError(f"day {day} is outside the requested window")

        for group in result.get("Groups", []):
            saw_group = True
            name = _group_name(group["Keys"][0], tag_key)
            amount = _amount(group["Metrics"][METRIC])
            bucket[name] = bucket.get(name, Decimal("0")) + amount

    if not saw_group:
        raise CostDataError(
            f"Cost Explorer returned no cost groups for {window.previous_start} to {window.end}"
        )
    return WeeklyCosts(current=current, previous=previous)


def _results_by_time(client, request: dict):
    """Yield every ResultsByTime entry, following NextPageToken."""
    token = None
    pages = 0
    while True:
        kwargs = dict(request)
        if token:
            kwargs["NextPageToken"] = token
        # API errors are not caught here on purpose; the caller should see them.
        response = client.get_cost_and_usage(**kwargs)
        pages += 1
        results = response.get("ResultsByTime")
        if not results and pages == 1:
            raise CostDataError("Cost Explorer returned an empty ResultsByTime")
        yield from results or []
        token = response.get("NextPageToken")
        if not token:
            return


def _group_name(key: str, tag_key: str | None) -> str:
    if tag_key is None:
        return key
    # Tag keys come back as "team$web"; an empty value means untagged.
    _, _, value = key.partition("$")
    return value or UNTAGGED


def _amount(metric: dict) -> Decimal:
    unit = metric.get("Unit")
    if unit != "USD":
        raise CostDataError(f"expected USD, got unit {unit!r}")
    # Cost Explorer sends amounts as strings; keep them exact.
    return Decimal(metric["Amount"])
