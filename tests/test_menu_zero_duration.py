"""Compatibility and timing regressions for instantaneous menu items."""

import pytest

from grantkit.menu import (
    item_cost,
    load_portfolio,
    run_gates,
    selection_cost,
    validate_menu,
    validate_rates,
    validate_selection,
)


def _zero_duration_menu(portfolio_menu, *, schema="grantkit-menu/v0"):
    menu = portfolio_menu
    menu["schema"] = schema
    menu["overheads"]["fiscal_sponsorship_rate"] = 0
    beta = menu["items"][2]
    beta["duration_months"] = 0
    beta["resourcing"] = {"fte_months": {"Program Lead": 4}}
    return menu


def _selection(*, schema="grantkit-selection/v0", start_month=None):
    line = {"item": "beta", "fraction": 1.0}
    if start_month is not None:
        line["start_month"] = start_month
    selection = {
        "schema": schema,
        "id": "zero-duration",
        "funder": "Synthetic Fund",
        "status": "draft",
        "window_months": 12,
        "selections": [line],
    }
    if schema == "grantkit-selection/v1":
        selection["horizon_months"] = 12
    return selection


def test_v0_zero_duration_probe_preserves_v03_total(
    make_portfolio, portfolio_menu, portfolio_rates
):
    menu = _zero_duration_menu(portfolio_menu)
    selection = _selection()
    assert validate_menu(menu) == []
    assert validate_rates(portfolio_rates) == []
    assert validate_selection(selection, menu) == []

    root = make_portfolio(
        menu=menu,
        rates=portfolio_rates,
        selections=[selection],
    )
    portfolio = load_portfolio(root)
    assert not any(
        finding.level == "error"
        for finding in run_gates(portfolio, "zero-duration")
    )
    cost = selection_cost(portfolio.get_selection("zero-duration"), portfolio)

    assert cost.total_usd == pytest.approx(60000.0)
    assert cost.items[0].duration_months == 0
    assert cost.periods[0]["cost"]["labor"] == pytest.approx(60000.0)
    assert cost.periods[0]["cost"]["total"] == pytest.approx(60000.0)


def test_instantaneous_cost_at_annual_boundary_lands_in_start_period(
    make_portfolio, portfolio_menu, portfolio_rates
):
    menu = _zero_duration_menu(portfolio_menu, schema="grantkit-menu/v1")
    selection = _selection(schema="grantkit-selection/v1", start_month=12)
    root = make_portfolio(
        menu=menu,
        rates=portfolio_rates,
        selections=[selection],
    )
    portfolio = load_portfolio(root)
    cost = selection_cost(portfolio.get_selection("zero-duration"), portfolio)

    assert [period["label"] for period in cost.periods] == ["Y1", "Y2"]
    assert [period["cost"]["labor"] for period in cost.periods] == [
        pytest.approx(0.0),
        pytest.approx(60000.0),
    ]
    assert cost.outside_window_usd == pytest.approx(60000.0)


def test_zero_duration_is_not_coerced_for_roster_or_non_personnel(
    make_portfolio, portfolio_menu, portfolio_rates
):
    menu = _zero_duration_menu(portfolio_menu, schema="grantkit-menu/v1")
    menu["items"][2]["resourcing"] = {
        "roster": [{"role": "Program Lead", "fte": 1.0}],
        "non_personnel_usd_per_year": 12000,
    }
    assert validate_menu(menu) == []
    root = make_portfolio(menu=menu, rates=portfolio_rates)
    portfolio = load_portfolio(root)

    cost = item_cost(
        portfolio.menu.get_item("beta"),
        portfolio.rates,
        portfolio.menu.unit_costs,
    )

    assert cost.roster_lines[0]["months"] == 0
    assert cost.labor_usd == 0
    assert cost.non_personnel_usd == 0
    assert cost.one_time_usd == 0


def test_zero_duration_org_base_is_instantaneous_not_window_spread(
    make_portfolio, portfolio_menu, portfolio_rates
):
    menu = _zero_duration_menu(portfolio_menu, schema="grantkit-menu/v1")
    org_base = menu["items"][0]
    org_base["duration_months"] = 0
    selection = {
        "schema": "grantkit-selection/v1",
        "id": "zero-duration-base",
        "funder": "Synthetic Fund",
        "status": "draft",
        "window_months": 24,
        "horizon_months": 24,
        "org_base": {"item": "org-floor", "fraction": 0.5},
        "selections": [],
    }
    root = make_portfolio(
        menu=menu,
        rates=portfolio_rates,
        selections=[selection],
    )
    portfolio = load_portfolio(root)
    cost = selection_cost(
        portfolio.get_selection("zero-duration-base"), portfolio
    )

    assert cost.org_base_usd == pytest.approx(600000.0)
    assert [period["cost"]["org_base"] for period in cost.periods] == [
        pytest.approx(600000.0),
        pytest.approx(0.0),
    ]


def test_completion_revenue_for_zero_duration_starts_at_item_start(
    make_portfolio, portfolio_menu, portfolio_rates
):
    menu = _zero_duration_menu(portfolio_menu, schema="grantkit-menu/v1")
    menu["items"][2]["revenue"] = [
        {
            "stream": "instant-enabled",
            "family": "earned",
            "unit": "delivery",
            "price_usd": 2,
            "volume_per_year": [120],
            "starts": "completion",
        }
    ]
    selection = _selection(schema="grantkit-selection/v1", start_month=0)
    root = make_portfolio(
        menu=menu,
        rates=portfolio_rates,
        selections=[selection],
    )
    portfolio = load_portfolio(root)
    cost = selection_cost(portfolio.get_selection("zero-duration"), portfolio)

    stream = cost.revenue["by_stream"][0]
    assert stream["start_month"] == 0
    assert stream["enabled_usd"] == pytest.approx(240.0)
