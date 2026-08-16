"""Multi-selection funding-rollup compiler and gate tests."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from grantkit.cli import main
from grantkit.core.checks import CheckResult
from grantkit.menu import (
    compile_combined,
    load_portfolio,
    run_combined_gates,
    selection_cost,
)
from grantkit.menu.render import (
    combined_budget_json,
    combined_budget_markdown,
)


def _invoke(*args: object):
    return CliRunner().invoke(main, ["budget", *map(str, args)])


def test_coverage_ledger_has_stacked_claims_and_explicit_gap(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["org_base"] = {
        "item": "org-floor",
        "fraction": 0.25,
    }
    portfolio = load_portfolio(make_portfolio(selections=portfolio_selections))
    combined = compile_combined(portfolio, ["sel-live-b", "sel-live-a"])

    assert combined.selection_ids == ["sel-live-a", "sel-live-b"]
    coverage = combined.org_bases[0]
    assert coverage["coverage_fraction"] == pytest.approx(0.35)
    assert coverage["gap_fraction"] == pytest.approx(0.65)
    assert coverage["item_one_time_usd"] == pytest.approx(1_200_000)
    assert coverage["shares"] == [
        {
            "kind": "selection",
            "claim_kind": "org_base",
            "selection_id": "sel-live-a",
            "funder": "Synthetic Fund A",
            "fraction": pytest.approx(0.1),
            "funded_usd": pytest.approx(120_000),
        },
        {
            "kind": "selection",
            "claim_kind": "org_base",
            "selection_id": "sel-live-b",
            "funder": "Synthetic Fund B",
            "fraction": pytest.approx(0.25),
            "funded_usd": pytest.approx(300_000),
        },
        {
            "kind": "gap",
            "claim_kind": "gap",
            "selection_id": None,
            "funder": "Unclaimed",
            "fraction": pytest.approx(0.65),
            "funded_usd": pytest.approx(780_000),
        },
    ]


def test_combined_categories_and_total_are_sums(make_portfolio):
    portfolio = load_portfolio(make_portfolio())
    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])
    costs = [
        selection_cost(portfolio.get_selection(selection_id), portfolio)
        for selection_id in combined.selection_ids
    ]

    assert combined.total_usd == pytest.approx(
        sum(cost.total_usd for cost in costs)
    )
    assert combined.categories["labor_usd"] == pytest.approx(
        sum(cost.labor_usd for cost in costs)
    )
    assert combined.categories["org_base_usd"] == pytest.approx(
        sum(cost.org_base_usd for cost in costs)
    )
    alpha = next(item for item in combined.items if item["item_id"] == "alpha")
    assert alpha["fraction"] == pytest.approx(1.0)
    assert alpha["over_allocated"] is False
    assert [share["selection_id"] for share in alpha["shares"]] == [
        "sel-live-a",
        "sel-live-b",
    ]


def test_fully_covered_base_retains_explicit_zero_gap(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["org_base"] = {
        "item": "org-floor",
        "fraction": 0.9,
    }
    portfolio = load_portfolio(make_portfolio(selections=portfolio_selections))
    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])

    coverage = combined.org_bases[0]
    assert coverage["coverage_fraction"] == pytest.approx(1.0)
    assert coverage["gap_fraction"] == pytest.approx(0.0)
    assert coverage["shares"][-1] == {
        "kind": "gap",
        "claim_kind": "gap",
        "selection_id": None,
        "funder": "Unclaimed",
        "fraction": pytest.approx(0.0),
        "funded_usd": pytest.approx(0.0),
    }


def test_shared_org_base_roster_counts_once_in_staffing(
    make_portfolio,
    portfolio_menu,
    portfolio_selections,
):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    org_base = portfolio_menu["items"][0]
    org_base["duration_months"] = 12
    org_base["resourcing"] = {
        "roster": [{"role": "Program Lead", "fte": 1, "months": 12}],
        "overhead_included": True,
    }
    portfolio_selections[1]["org_base"] = {
        "item": "org-floor",
        "fraction": 0.4,
    }
    portfolio = load_portfolio(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    )

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])
    period = combined.periods[0]
    assert period["base_fte_by_role"]["Program Lead"] == pytest.approx(1.0)
    assert period["fte_by_role"]["Encoding Lead"] == pytest.approx(0.5)
    assert period["total_fte_by_role"]["Program Lead"] == pytest.approx(1.0)
    # Personnel is the funded-spend attribution: 10% + 40% of the
    # 12-FTE-month base. It is intentionally distinct from operational FTE.
    assert combined.personnel["Program Lead"]["fte_months"] == pytest.approx(
        6.0
    )


def test_mixed_period_lengths_normalize_incremental_fte_to_combined_period(
    make_portfolio,
    portfolio_menu,
    portfolio_selections,
):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    alpha = portfolio_menu["items"][1]
    alpha["duration_months"] = 13
    alpha["dependencies"] = []
    alpha["resourcing"] = {"fte_months": {"Program Lead": 13}}
    beta = portfolio_menu["items"][2]
    beta["duration_months"] = 24
    beta["resourcing"] = {"fte_months": {"Program Lead": 24}}
    portfolio_selections[0]["window_months"] = 13
    portfolio_selections[0].pop("org_base")
    portfolio_selections[0]["selections"] = [
        {"item": "alpha", "fraction": 1.0}
    ]
    portfolio_selections[1]["window_months"] = 24
    portfolio_selections[1]["selections"] = [{"item": "beta", "fraction": 1.0}]
    portfolio = load_portfolio(
        make_portfolio(
            menu=portfolio_menu,
            selections=portfolio_selections[:2],
        )
    )

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])

    assert combined.periods[1]["months"] == pytest.approx(12)
    # Alpha contributes one FTE-month and beta contributes twelve in Y2.
    assert combined.periods[1]["fte_by_role"]["Program Lead"] == pytest.approx(
        13 / 12
    )


def test_mixed_period_lengths_normalize_shared_base_once(
    make_portfolio,
    portfolio_menu,
    portfolio_selections,
):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    org_base = portfolio_menu["items"][0]
    org_base["duration_months"] = 13
    org_base["resourcing"] = {
        "roster": [{"role": "Program Lead", "fte": 1, "months": 13}],
        "overhead_included": True,
    }
    portfolio_selections[0]["window_months"] = 13
    portfolio_selections[0]["org_base"]["fraction"] = 0.5
    portfolio_selections[0]["selections"] = []
    portfolio_selections[1]["window_months"] = 24
    portfolio_selections[1]["org_base"] = {
        "item": "org-floor",
        "fraction": 0.5,
    }
    portfolio_selections[1]["selections"] = []
    portfolio = load_portfolio(
        make_portfolio(
            menu=portfolio_menu,
            selections=portfolio_selections[:2],
        )
    )

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])

    assert combined.periods[1]["months"] == pytest.approx(12)
    # The shared roster is active for one month in the twelve-month Y2.
    assert combined.periods[1]["base_fte_by_role"][
        "Program Lead"
    ] == pytest.approx(1 / 12)


def test_ordinary_org_base_roster_is_operational_base_once(
    make_portfolio,
    portfolio_menu,
    portfolio_selections,
):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    org_base = portfolio_menu["items"][0]
    org_base["duration_months"] = 12
    org_base["resourcing"] = {
        "roster": [{"role": "Program Lead", "fte": 1, "months": 12}],
        "overhead_included": True,
    }
    for selection in portfolio_selections[:2]:
        selection.pop("org_base", None)
        selection["selections"] = [{"item": "org-floor", "fraction": 0.25}]
    portfolio = load_portfolio(
        make_portfolio(
            menu=portfolio_menu,
            selections=portfolio_selections[:2],
        )
    )

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])
    period = combined.periods[0]

    assert period["fte_by_role"] == {}
    assert period["base_fte_by_role"]["Program Lead"] == pytest.approx(1)
    assert period["total_fte_by_role"]["Program Lead"] == pytest.approx(1)
    # Funded attribution remains two quarter-shares of the twelve-month seat.
    assert combined.personnel["Program Lead"]["fte_months"] == pytest.approx(6)
    assert combined.categories["labor_usd"] == pytest.approx(90_000)
    assert combined.categories["org_base_usd"] == pytest.approx(0)


def test_mixed_org_base_claim_routes_do_not_mix_base_and_incremental_roster(
    make_portfolio,
    portfolio_menu,
    portfolio_selections,
):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    org_base = portfolio_menu["items"][0]
    org_base["duration_months"] = 12
    org_base["resourcing"] = {
        "roster": [{"role": "Program Lead", "fte": 1, "months": 12}],
        "overhead_included": True,
    }
    portfolio_selections[0]["org_base"]["fraction"] = 0.4
    portfolio_selections[0]["selections"] = []
    portfolio_selections[1].pop("org_base", None)
    portfolio_selections[1]["selections"] = [
        {"item": "org-floor", "fraction": 0.6}
    ]
    portfolio = load_portfolio(
        make_portfolio(
            menu=portfolio_menu,
            selections=portfolio_selections[:2],
        )
    )

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])
    period = combined.periods[0]

    assert period["fte_by_role"] == {}
    assert period["base_fte_by_role"]["Program Lead"] == pytest.approx(1)
    assert period["total_fte_by_role"]["Program Lead"] == pytest.approx(1)
    assert combined.personnel["Program Lead"]["fte_months"] == pytest.approx(
        12
    )
    assert combined.categories["labor_usd"] == pytest.approx(108_000)
    assert combined.categories["org_base_usd"] == pytest.approx(72_000)


def test_org_base_coverage_uses_item_and_org_base_c2_claims(
    make_portfolio,
    portfolio_selections,
):
    portfolio_selections[0]["org_base"]["fraction"] = 0.6
    portfolio_selections[1]["selections"].append(
        {"item": "org-floor", "fraction": 0.6}
    )
    portfolio = load_portfolio(make_portfolio(selections=portfolio_selections))

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])
    coverage = combined.org_bases[0]

    assert coverage["coverage_fraction"] == pytest.approx(1.2)
    assert coverage["gap_fraction"] == pytest.approx(0.0)
    assert coverage["over_allocated"] is True
    assert [
        (share["selection_id"], share["kind"], share["claim_kind"])
        for share in coverage["shares"]
    ] == [
        ("sel-live-a", "selection", "org_base"),
        ("sel-live-b", "selection", "item"),
        (None, "gap", "gap"),
    ]
    ordinary = next(
        item for item in combined.items if item["item_id"] == "org-floor"
    )
    assert ordinary["fraction"] == pytest.approx(0.6)
    assert ordinary["over_allocated"] is False


def test_combined_revenue_enables_shared_stream_once_and_stacks_attribution(
    make_portfolio,
    portfolio_menu,
):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    alpha = portfolio_menu["items"][1]
    alpha["revenue"] = [
        {
            "stream": "licenses",
            "price_usd": 100,
            "volume_per_year": [120],
            "starts": "start",
        }
    ]
    portfolio = load_portfolio(make_portfolio(menu=portfolio_menu))

    combined = compile_combined(portfolio, ["sel-live-a", "sel-live-b"])
    stream = combined.revenue["by_stream"][0]
    assert stream["enabled_usd"] == pytest.approx(12_000)
    assert stream["attributed_usd"] == pytest.approx(12_000)
    assert [share["attributed_usd"] for share in stream["shares"]] == [
        pytest.approx(6_000),
        pytest.approx(6_000),
    ]


def test_combined_gates_force_draft_live_and_scope_to_selected_set(
    make_portfolio,
):
    portfolio = load_portfolio(make_portfolio())
    findings = run_combined_gates(portfolio, ["sel-live-a", "sel-draft"])
    c2 = [
        finding
        for finding in findings
        if finding.rule == "cofunding_over_allocated"
    ]
    assert len(c2) == 1
    assert "sel-draft 0.8 + sel-live-a 0.5 = 1.3" in c2[0].message
    assert "sel-live-b" not in c2[0].message


def test_combined_json_and_markdown_are_deterministic(make_portfolio):
    portfolio = load_portfolio(make_portfolio())
    ids = ["sel-live-a", "sel-live-b"]
    gates = CheckResult(items=run_combined_gates(portfolio, ids))
    first = compile_combined(portfolio, ids)
    second = compile_combined(portfolio, list(reversed(ids)))
    first_payload = combined_budget_json(portfolio, first, gates)
    second_payload = combined_budget_json(portfolio, second, gates)

    assert json.dumps(
        first_payload, indent=2, sort_keys=True, allow_nan=False
    ) == json.dumps(second_payload, indent=2, sort_keys=True, allow_nan=False)
    assert combined_budget_markdown(
        portfolio, first, gates
    ) == combined_budget_markdown(portfolio, second, gates)


def test_combine_cli_json_surfaces_over_allocation(make_portfolio):
    result = _invoke(
        "--combine",
        "sel-draft,sel-live-a",
        "--json",
        make_portfolio(),
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema"] == "grantkit-combined-budget/v1"
    assert payload["selection_ids"] == ["sel-draft", "sel-live-a"]
    alpha = next(
        item for item in payload["items"] if item["item_id"] == "alpha"
    )
    assert alpha["fraction"] == pytest.approx(1.3)
    assert alpha["over_allocated"] is True
    assert payload["gates"]["errors"] == 1
    assert payload["gates"]["items"][0]["rule"] == ("cofunding_over_allocated")


def test_combine_cli_json_is_byte_stable_and_input_order_independent(
    make_portfolio,
):
    root = make_portfolio()
    first = _invoke("--combine", "sel-live-a,sel-live-b", "--json", root)
    second = _invoke("--combine", "sel-live-b,sel-live-a", "--json", root)

    assert first.exit_code == second.exit_code == 0
    assert first.stdout_bytes == second.stdout_bytes


def test_combine_cli_markdown_has_coverage_gap_and_gates(
    make_portfolio, tmp_path
):
    output = tmp_path / "combined.md"
    result = _invoke(
        "--combine",
        "sel-live-b,sel-live-a",
        "--output",
        output,
        make_portfolio(),
    )
    assert result.exit_code == 0, result.output
    text = output.read_text(encoding="utf-8")
    assert "## Funding coverage" in text
    assert "Core-ops coverage: **10%**" in text
    assert "Unclaimed | — | 90%" in text
    assert "## Combined staffing" in text
    assert "## Gates" in text


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--combine", "sel-live-a", "--json"), "at least two"),
        (
            ("--combine", "sel-live-a,sel-live-a", "--json"),
            "cannot repeat",
        ),
        (
            ("--combine", "sel-live-a,sel-live-b"),
            "requires --json and/or --output",
        ),
        (
            (
                "--combine",
                "sel-live-a,sel-live-b",
                "--selection",
                "sel-live-a",
                "--json",
            ),
            "--selection cannot be used with --combine",
        ),
    ],
)
def test_combine_cli_rejects_invalid_modes(make_portfolio, args, message):
    result = _invoke(*args, make_portfolio())
    assert result.exit_code == 2
    assert message in result.output
