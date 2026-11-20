from botocore.exceptions import ClientError

from cost_report.cli import main
from tests.fakes import FakeCostExplorer, load


def full_client():
    return FakeCostExplorer(
        {
            "SERVICE": [load("service_page1.json"), load("service_page2.json")],
            "team": [load("tag_team.json")],
        }
    )


def test_writes_report_file(tmp_path):
    out = tmp_path / "report.md"
    code = main(
        ["--end", "2026-11-16", "--tag", "team", "--top", "3", "--output", str(out)],
        client=full_client(),
    )
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "## Top 3 services" in text
    assert "(untagged)" in text


def test_prints_to_stdout(capsys):
    assert main(["--end", "2026-11-16"], client=full_client()) == 0
    assert "## Executive summary" in capsys.readouterr().out


def test_api_error_exits_non_zero_and_writes_nothing(tmp_path, capsys):
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow"}}, "GetCostAndUsage"
    )
    out = tmp_path / "report.md"
    code = main(["--end", "2026-11-16", "--output", str(out)], client=FakeCostExplorer(error=error))
    assert code == 1
    assert not out.exists()
    assert "ThrottlingException" in capsys.readouterr().err


def test_empty_data_exits_non_zero(capsys):
    client = FakeCostExplorer({"SERVICE": [{"ResultsByTime": []}]})
    assert main(["--end", "2026-11-16"], client=client) == 1
    assert "CostDataError" in capsys.readouterr().err
