"""Turn weekly cost totals into a Markdown executive report. No I/O here."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cost_report.explorer import UNTAGGED, WeeklyCosts, WeekWindow

ZERO = Decimal("0")


@dataclass(frozen=True)
class Row:
    name: str
    current: Decimal
    previous: Decimal

    @property
    def change(self) -> Decimal:
        return self.current - self.previous


def rank(costs: WeeklyCosts, top_n: int) -> list[Row]:
    """Top N by this week's spend, plus one "Other" row for the rest."""
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    names = set(costs.current) | set(costs.previous)
    rows = [Row(n, costs.current.get(n, ZERO), costs.previous.get(n, ZERO)) for n in names]
    # Highest spend first; name breaks ties so output is stable.
    rows.sort(key=lambda r: (-r.current, -r.previous, r.name))
    top, rest = rows[:top_n], rows[top_n:]
    if rest:
        top.append(
            Row(
                f"Other ({len(rest)})",
                sum((r.current for r in rest), ZERO),
                sum((r.previous for r in rest), ZERO),
            )
        )
    return top


def money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def signed_money(value: Decimal) -> str:
    return ("+" if value >= 0 else "") + money(value)


def pct_change(current: Decimal, previous: Decimal) -> str:
    if previous == 0:
        return "new" if current > 0 else "0.0%"
    pct = (current - previous) / previous * 100
    return f"{pct:+.1f}%"


def build_report(
    window: WeekWindow,
    by_service: WeeklyCosts,
    top_n: int = 5,
    tag_key: str | None = None,
    by_tag: WeeklyCosts | None = None,
) -> str:
    if (tag_key is None) != (by_tag is None):
        raise ValueError("tag_key and by_tag must be given together")

    total_now = sum(by_service.current.values(), ZERO)
    total_before = sum(by_service.previous.values(), ZERO)
    service_rows = rank(by_service, top_n)

    lines = [
        f"# Weekly AWS cost report: {window.current_start} to {window.end}",
        "",
        f"_Week ends {window.end} (exclusive). Compared with {window.previous_start} "
        f"to {window.current_start}. Metric: unblended cost, USD._",
        "",
        "## Executive summary",
        "",
    ]
    lines += _summary(total_now, total_before, by_service, tag_key, by_tag)
    lines += ["", f"## Top {top_n} services", ""]
    lines += _table("Service", service_rows, total_now)

    if tag_key is not None and by_tag is not None:
        lines += ["", f"## Top {top_n} by tag `{tag_key}`", ""]
        lines += _table(tag_key, rank(by_tag, top_n), sum(by_tag.current.values(), ZERO))

    return "\n".join(lines) + "\n"


def _summary(total_now, total_before, by_service, tag_key, by_tag) -> list[str]:
    out = [
        f"- Total spend this week: **{money(total_now)}** "
        f"({signed_money(total_now - total_before)}, "
        f"{pct_change(total_now, total_before)} vs last week's {money(total_before)})."
    ]

    full = rank(by_service, max(len(by_service.current) + len(by_service.previous), 1))
    if full and full[0].current > 0:
        top = full[0]
        out.append(
            f"- Largest cost driver: **{top.name}** at {money(top.current)} "
            f"({_share(top.current, total_now)} of total)."
        )

    risers = [r for r in full if r.change > 0]
    if risers:
        mover = max(risers, key=lambda r: (r.change, r.name))
        out.append(
            f"- Biggest increase: **{mover.name}**, {signed_money(mover.change)} "
            f"({pct_change(mover.current, mover.previous)})."
        )
    else:
        out.append("- No service increased week over week.")

    if tag_key is not None and by_tag is not None:
        untagged = by_tag.current.get(UNTAGGED, ZERO)
        tag_total = sum(by_tag.current.values(), ZERO)
        out.append(
            f"- Spend without a `{tag_key}` tag: {money(untagged)} "
            f"({_share(untagged, tag_total)} of tagged-view total)."
        )
    return out


def _share(part: Decimal, total: Decimal) -> str:
    if total == 0:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


def _table(label: str, rows: list[Row], total: Decimal) -> list[str]:
    out = [
        f"| {label} | This week | Last week | Change | Change % | Share |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        out.append(
            f"| {r.name} | {money(r.current)} | {money(r.previous)} | "
            f"{signed_money(r.change)} | {pct_change(r.current, r.previous)} | "
            f"{_share(r.current, total)} |"
        )
    return out
