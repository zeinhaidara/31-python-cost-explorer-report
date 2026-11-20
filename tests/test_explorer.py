from datetime import date
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from cost_report.explorer import UNTAGGED, CostDataError, WeekWindow, fetch_weekly_costs
from tests.fakes import FakeCostExplorer, load

WINDOW = WeekWindow(end=date(2026, 11, 16))
EC2 = "Amazon Elastic Compute Cloud - Compute"


def service_client():
    return FakeCostExplorer({"SERVICE": [load("service_page1.json"), load("service_page2.json")]})


def test_window_boundaries():
    assert WINDOW.previous_start == date(2026, 11, 2)
    assert WINDOW.current_start == date(2026, 11, 9)


def test_request_shape():
    client = service_client()
    fetch_weekly_costs(client, WINDOW)
    first = client.calls[0]
    assert first["TimePeriod"] == {"Start": "2026-11-02", "End": "2026-11-16"}
    assert first["Granularity"] == "DAILY"
    assert first["Metrics"] == ["UnblendedCost"]
    assert first["GroupBy"] == [{"Type": "DIMENSION", "Key": "SERVICE"}]
    assert "NextPageToken" not in first


def test_follows_next_page_token():
    client = service_client()
    costs = fetch_weekly_costs(client, WINDOW)
    assert len(client.calls) == 2
    assert client.calls[1]["NextPageToken"] == "page-2"
    # Current-week data only lives on page 2, so it proves page 2 was read.
    assert costs.current["AmazonCloudWatch"] == Decimal("5.00")


def test_amounts_are_exact_decimals():
    costs = fetch_weekly_costs(service_client(), WINDOW)
    assert costs.previous[EC2] == Decimal("200.20")
    assert costs.current[EC2] == Decimal("300.246912")
    # 0.2 + 0.2 must be exactly 0.4, which float addition would not promise.
    assert costs.current["AWS Lambda"] == Decimal("0.4")
    assert isinstance(costs.current[EC2], Decimal)


def test_days_split_into_the_right_week():
    costs = fetch_weekly_costs(service_client(), WINDOW)
    assert "AmazonCloudWatch" not in costs.previous
    assert costs.previous["AWS Lambda"] == Decimal("0.1")
    assert sum(costs.previous.values()) == Decimal("340.40")
    assert sum(costs.current.values()) == Decimal("445.636912")


def test_tag_grouping_and_untagged_line():
    client = FakeCostExplorer({"team": [load("tag_team.json")]})
    costs = fetch_weekly_costs(client, WINDOW, tag_key="team")
    assert client.calls[0]["GroupBy"] == [{"Type": "TAG", "Key": "team"}]
    assert costs.current == {
        "web": Decimal("250.00"),
        "data": Decimal("120.636912"),
        UNTAGGED: Decimal("75.00"),
    }
    assert costs.previous[UNTAGGED] == Decimal("90.40")


def test_api_error_propagates():
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}}, "GetCostAndUsage"
    )
    with pytest.raises(ClientError, match="AccessDeniedException"):
        fetch_weekly_costs(FakeCostExplorer(error=error), WINDOW)


def test_empty_results_fail_loudly():
    client = FakeCostExplorer({"SERVICE": [{"ResultsByTime": []}]})
    with pytest.raises(CostDataError, match="empty ResultsByTime"):
        fetch_weekly_costs(client, WINDOW)


def test_days_without_any_groups_fail_loudly():
    page = {
        "ResultsByTime": [
            {"TimePeriod": {"Start": "2026-11-10", "End": "2026-11-11"}, "Groups": []}
        ]
    }
    with pytest.raises(CostDataError, match="no cost groups"):
        fetch_weekly_costs(FakeCostExplorer({"SERVICE": [page]}), WINDOW)


def test_non_usd_unit_is_rejected():
    page = load("tag_team.json")
    page["ResultsByTime"][0]["Groups"][0]["Metrics"]["UnblendedCost"]["Unit"] = "EUR"
    with pytest.raises(CostDataError, match="EUR"):
        fetch_weekly_costs(FakeCostExplorer({"team": [page]}), WINDOW, tag_key="team")


def test_day_outside_window_is_rejected():
    page = load("tag_team.json")
    page["ResultsByTime"][0]["TimePeriod"]["Start"] = "2026-10-01"
    with pytest.raises(CostDataError, match="outside"):
        fetch_weekly_costs(FakeCostExplorer({"team": [page]}), WINDOW, tag_key="team")


def test_blank_tag_key_is_rejected():
    with pytest.raises(ValueError):
        fetch_weekly_costs(FakeCostExplorer(), WINDOW, tag_key="  ")
