from datetime import date
from decimal import Decimal

import pytest

from cost_report.explorer import UNTAGGED, WeeklyCosts, WeekWindow
from cost_report.report import build_report, money, pct_change, rank

D = Decimal
WINDOW = WeekWindow(end=date(2026, 11, 16))

SERVICES = WeeklyCosts(
    current={
        "EC2": D("300.246912"),
        "RDS": D("100.00"),
        "S3": D("39.99"),
        "CloudWatch": D("5.00"),
        "Lambda": D("0.4"),
    },
    previous={
        "EC2": D("200.20"),
        "RDS": D("100.00"),
        "S3": D("40.10"),
        "Lambda": D("0.1"),
        "Glue": D("12.00"),
    },
)
TAGS = WeeklyCosts(
    current={"web": D("250"), "data": D("120.636912"), UNTAGGED: D("75")},
    previous={"web": D("150"), "data": D("100"), UNTAGGED: D("90.40")},
)


def test_rank_keeps_top_n_and_rolls_up_the_rest():
    rows = rank(SERVICES, 2)
    assert [r.name for r in rows] == ["EC2", "RDS", "Other (4)"]
    other = rows[-1]
    assert other.current == D("45.39")  # S3 + CloudWatch + Lambda + Glue(0)
    assert other.previous == D("52.20")  # S3 + Lambda + Glue


def test_rank_includes_services_that_dropped_to_zero():
    names = [r.name for r in rank(SERVICES, 10)]
    assert names[-1] == "Glue"
    assert "Other" not in " ".join(names)


def test_rank_rejects_zero():
    with pytest.raises(ValueError):
        rank(SERVICES, 0)


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (D("150"), D("100"), "+50.0%"),
        (D("50"), D("100"), "-50.0%"),
        (D("5"), D("0"), "new"),
        (D("0"), D("0"), "0.0%"),
        (D("0"), D("12"), "-100.0%"),
    ],
)
def test_pct_change(current, previous, expected):
    assert pct_change(current, previous) == expected


def test_money_formatting():
    assert money(D("1234.5")) == "$1,234.50"
    assert money(D("-0.115")) == "-$0.12"


def test_report_has_summary_before_tables():
    md = build_report(WINDOW, SERVICES, top_n=3)
    assert md.startswith("# Weekly AWS cost report: 2026-11-09 to 2026-11-16")
    assert md.index("## Executive summary") < md.index("## Top 3 services")


def test_summary_numbers():
    md = build_report(WINDOW, SERVICES, top_n=3)
    # 445.636912 now vs 352.40 before
    assert "Total spend this week: **$445.64** (+$93.24, +26.5% vs last week's $352.40)" in md
    assert "Largest cost driver: **EC2** at $300.25 (67.4% of total)" in md
    assert "Biggest increase: **EC2**, +$100.05 (+50.0%)" in md


def test_service_table_rows():
    md = build_report(WINDOW, SERVICES, top_n=3)
    assert "| EC2 | $300.25 | $200.20 | +$100.05 | +50.0% | 67.4% |" in md
    assert "| Other (3) | $5.40 | $12.10 | -$6.70 | -55.4% | 1.2% |" in md


def test_no_increase_is_stated():
    flat = WeeklyCosts(current={"EC2": D("10")}, previous={"EC2": D("20")})
    md = build_report(WINDOW, flat)
    assert "No service increased week over week." in md
    assert "Biggest increase" not in md


def test_tag_section_and_untagged_line():
    md = build_report(WINDOW, SERVICES, top_n=5, tag_key="team", by_tag=TAGS)
    assert "## Top 5 by tag `team`" in md
    assert f"| {UNTAGGED} | $75.00 | $90.40 | -$15.40 | -17.0% | 16.8% |" in md
    assert "Spend without a `team` tag: $75.00 (16.8% of tagged-view total)" in md


def test_no_tag_section_without_tag():
    md = build_report(WINDOW, SERVICES)
    assert "by tag" not in md
    assert "without a" not in md


def test_tag_key_and_data_must_come_together():
    with pytest.raises(ValueError):
        build_report(WINDOW, SERVICES, tag_key="team")
