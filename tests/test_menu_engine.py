"""Tests for the pure budget-compilation engine.

Hand-computed expectations for the synthetic portfolio (see conftest):

* alpha    labor = 6/12 x 320,000 + 3/12 x 195,000 = 208,750
* beta     labor = 4/12 x 180,000 = 60,000; contract 20,000 -> 80,000
* gamma    units = 10,000 x 2.5 = 25,000
* delta    recurring 60,000/yr, no one-time cost
* org-floor flat 1,200,000, fee-inclusive (overhead_included)
* sel-live-a (window 12, org base 0.1, overhead 7%):
    work     = 0.5 x 208,750 + 0.5 x 25,000 = 116,875
    org base = 0.1 x 1,200,000 = 120,000 (excluded from overhead)
    overhead = 0.07 x 116,875 = 8,181.25
    total    = 245,056.25; fit = 245,056.25 / 500,000
"""

import pytest

from grantkit.menu import (
    compile_selection,
    item_cost,
    load_portfolio,
    selection_cost,
)


@pytest.fixture
def portfolio(make_portfolio):
    return load_portfolio(make_portfolio())


def _item(portfolio, item_id):
    return portfolio.menu.get_item(item_id)


def _cost(portfolio, item_id):
    return item_cost(
        _item(portfolio, item_id),
        portfolio.rates,
        portfolio.menu.unit_costs,
    )


# -- item_cost ----------------------------------------------------------


def test_labor_from_fte_months_and_loaded_rates(portfolio):
    cost = _cost(portfolio, "alpha")
    assert cost.labor_usd == pytest.approx(208750.0)
    assert cost.one_time_usd == pytest.approx(208750.0)
    assert cost.labor_by_role["Encoding Lead"]["usd"] == pytest.approx(
        160000.0
    )
    assert cost.labor_by_role["Research Engineer"][
        "fte_months"
    ] == pytest.approx(3.0)


def test_labor_plus_contract(portfolio):
    cost = _cost(portfolio, "beta")
    assert cost.labor_usd == pytest.approx(60000.0)
    assert cost.contract_usd == pytest.approx(20000.0)
    assert cost.one_time_usd == pytest.approx(80000.0)


def test_units_times_unit_price(portfolio):
    cost = _cost(portfolio, "gamma-units")
    assert cost.units_usd == pytest.approx(25000.0)
    assert cost.one_time_usd == pytest.approx(25000.0)


def test_recurring_excluded_from_one_time(portfolio):
    cost = _cost(portfolio, "delta-recurring")
    assert cost.one_time_usd == pytest.approx(0.0)
    assert cost.recurring_usd_per_year == pytest.approx(60000.0)


def test_flat_amount_and_overhead_inclusion_split(portfolio):
    included = _cost(portfolio, "org-floor")
    assert included.flat_usd == pytest.approx(1200000.0)
    assert included.overhead_bearing_one_time_usd == pytest.approx(0.0)
    bearing = _cost(portfolio, "shipped-item")
    assert bearing.overhead_bearing_one_time_usd == pytest.approx(50000.0)


def test_item_cost_raises_on_unknown_role(portfolio):
    item = _item(portfolio, "alpha")
    item.resourcing.fte_months["Nobody"] = 1
    with pytest.raises(KeyError):
        item_cost(item, portfolio.rates, portfolio.menu.unit_costs)


def test_item_cost_raises_on_unknown_unit(portfolio):
    item = _item(portfolio, "gamma-units")
    item.resourcing.units["widget"] = 5
    with pytest.raises(KeyError):
        item_cost(item, portfolio.rates, portfolio.menu.unit_costs)


# -- selection_cost -----------------------------------------------------


def test_selection_cost_full_arithmetic(portfolio):
    cost = selection_cost(portfolio.get_selection("sel-live-a"), portfolio)
    assert cost.labor_usd == pytest.approx(104375.0)
    assert cost.units_usd == pytest.approx(12500.0)
    assert cost.org_base_usd == pytest.approx(120000.0)
    assert cost.overhead_usd == pytest.approx(8181.25)
    assert cost.total_usd == pytest.approx(245056.25)
    assert cost.fit == pytest.approx(245056.25 / 500000)


def test_selection_cost_personnel_fraction_weighted(portfolio):
    cost = selection_cost(portfolio.get_selection("sel-live-a"), portfolio)
    lead = cost.personnel["Encoding Lead"]
    assert lead["fte_months"] == pytest.approx(3.0)
    assert lead["usd"] == pytest.approx(80000.0)
    assert lead["loaded_usd"] == pytest.approx(320000.0)
    engineer = cost.personnel["Research Engineer"]
    assert engineer["usd"] == pytest.approx(24375.0)


def test_recurring_prorated_by_window(make_portfolio, portfolio_selections):
    portfolio_selections[1]["window_months"] = 18
    portfolio = load_portfolio(make_portfolio(selections=portfolio_selections))
    cost = selection_cost(portfolio.get_selection("sel-live-b"), portfolio)
    assert cost.recurring_usd == pytest.approx(90000.0)
    # Recurring dollars bear overhead; alpha's labor share too.
    assert cost.overhead_usd == pytest.approx(0.07 * (104375.0 + 90000.0))
    assert cost.fit is None  # no target on sel-live-b


def test_org_base_not_prorated_by_window(make_portfolio, portfolio_selections):
    portfolio_selections[0]["window_months"] = 6
    portfolio = load_portfolio(make_portfolio(selections=portfolio_selections))
    cost = selection_cost(portfolio.get_selection("sel-live-a"), portfolio)
    # A flat org-base block is a fraction of a flat amount; the window
    # does not scale it.
    assert cost.org_base_usd == pytest.approx(120000.0)


def test_overhead_included_fee_applied_exactly_once(
    make_portfolio, portfolio_menu
):
    """The wild-bug regression: fee-inclusive blocks must not be
    re-inflated by the selection-level overhead."""
    portfolio = load_portfolio(make_portfolio(menu=portfolio_menu))
    cost = selection_cost(portfolio.get_selection("sel-live-a"), portfolio)
    work_bearing = 104375.0 + 12500.0
    assert cost.overhead_usd == pytest.approx(0.07 * work_bearing)
    assert cost.total_usd == pytest.approx(
        work_bearing + 120000.0 + 0.07 * work_bearing
    )

    # Flip the flag: the same block becomes overhead-bearing, and the
    # difference is exactly one fee on the org-base share.
    portfolio_menu["items"][0]["resourcing"]["overhead_included"] = False
    portfolio2 = load_portfolio(make_portfolio(menu=portfolio_menu))
    cost2 = selection_cost(portfolio2.get_selection("sel-live-a"), portfolio2)
    assert cost2.overhead_usd == pytest.approx(
        0.07 * (work_bearing + 120000.0)
    )
    assert cost2.total_usd - cost.total_usd == pytest.approx(0.07 * 120000.0)


def test_zero_fraction_line_preserved_but_costless(portfolio):
    cost = selection_cost(portfolio.get_selection("sel-draft"), portfolio)
    line = {item.item_id: item for item in cost.items}["beta"]
    assert line.fraction == 0.0
    assert line.funded_usd == pytest.approx(0.0)
    # Declarations add no personnel rows.
    assert "Program Lead" not in cost.personnel


def test_compile_is_deterministic(portfolio):
    selection = portfolio.get_selection("sel-live-a")
    first = selection_cost(selection, portfolio).to_dict()
    second = selection_cost(selection, portfolio).to_dict()
    assert first == second


def test_compile_selection_is_the_public_alias(portfolio):
    assert compile_selection is selection_cost


def test_selection_cost_raises_on_unknown_item(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["selections"].append(
        {"item": "zzz", "fraction": 0.1}
    )
    portfolio = load_portfolio(make_portfolio(selections=portfolio_selections))
    with pytest.raises(KeyError):
        selection_cost(portfolio.get_selection("sel-live-a"), portfolio)
