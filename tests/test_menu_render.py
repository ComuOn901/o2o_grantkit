"""Tests for budget rendering: rounding, markdown sections, narrative."""

import io
from pathlib import Path

import pytest
from rich.console import Console

from grantkit.menu import Portfolio, load_portfolio, selection_cost
from grantkit.menu.render import (
    budget_markdown,
    budget_narrative,
    format_money,
    generated_from,
    print_budget,
    round_half_up,
)


def _compiled(root, selection_id):
    portfolio = load_portfolio(root)
    selection = portfolio.get_selection(selection_id)
    return portfolio, selection, selection_cost(selection, portfolio)


def _extra_selection(item, fraction=1.0, sid="sel-extra"):
    return {
        "schema": "grantkit-selection/v0",
        "id": sid,
        "funder": "Synthetic Fund X",
        "status": "live",
        "window_months": 12,
        "selections": [{"item": item, "fraction": fraction}],
    }


# -- rounding -----------------------------------------------------------


def test_round_half_up_rounds_ties_up_not_bankers():
    # Decimal ROUND_HALF_UP, not Python's banker's rounding: 2.5 -> 3.
    assert round_half_up(2.5) == 3
    assert round_half_up(3.5) == 4
    assert round_half_up(0.499) == 0
    assert round_half_up(245056.25) == 245056


def test_format_money_whole_units_with_commas():
    assert format_money(1234.56, "USD") == "USD 1,235"
    assert format_money(0.0, "EUR") == "EUR 0"


# -- reproducibility line -----------------------------------------------


def test_generated_from_names_provider_and_scenario(make_portfolio):
    portfolio = load_portfolio(make_portfolio())
    text = generated_from(portfolio)
    assert "eggnest-employer 0.2.0" in text
    assert "2026-08-15" in text
    assert "scenario synthetic-tests" in text
    assert "Same inputs produce the same document." in text


def test_generated_from_unknown_provider():
    portfolio = Portfolio(root=Path("."), menu_data={}, rates_data={})
    text = generated_from(portfolio)
    assert "unknown provider" in text
    assert "scenario" not in text


# -- markdown document sections -----------------------------------------


def test_markdown_no_target_omits_target_lines(make_portfolio):
    # sel-live-b carries no target_usd: no Target line, no fit line.
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-b")
    text = budget_markdown(portfolio, selection, cost)
    assert "- Target:" not in text
    assert "Target fit:" not in text
    assert "- Window: 12 months" in text


def test_markdown_zero_categories_suppressed(make_portfolio):
    # sel-live-a has no contract or recurring dollars: those category
    # rows disappear instead of rendering USD 0.
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-a")
    text = budget_markdown(portfolio, selection, cost)
    assert "| Labor |" in text
    assert "| Units |" in text
    assert "| Org base |" in text
    assert "| Overhead (7%) |" in text
    assert "| Contracts |" not in text
    assert "| Recurring (prorated) |" not in text
    assert "| **Total** | **USD 245,056** |" in text


def test_markdown_personnel_mixed_benchmarks_use_dash(make_portfolio):
    # Encoding Lead carries a benchmark; Research Engineer does not —
    # the Benchmark column appears, with an em-dash filler.
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-a")
    text = budget_markdown(portfolio, selection, cost)
    assert "| Role | FTE-months | Loaded annual | Amount | Benchmark |" in text
    assert "BLS OEWS May 2024, SOC 15-1252, national, p75 = USD 130,560" in (
        text
    )
    assert "| — |" in text


def test_markdown_personnel_without_benchmarks_drops_column(
    make_portfolio, portfolio_selections
):
    # beta is costed with Program Lead only (no benchmark): the
    # personnel table renders without a Benchmark column.
    selections = portfolio_selections + [_extra_selection("beta")]
    portfolio, selection, cost = _compiled(
        make_portfolio(selections=selections), "sel-extra"
    )
    text = budget_markdown(portfolio, selection, cost)
    assert "## Personnel" in text
    assert "| Role | FTE-months | Loaded annual | Amount |\n" in text
    assert "Benchmark" not in text


def test_markdown_benchmark_without_source_is_silent(
    make_portfolio, portfolio_rates
):
    # A benchmark with no source string renders as no benchmark at all.
    portfolio_rates["roles"][0]["benchmark"] = {"percentile": 75}
    portfolio, selection, cost = _compiled(
        make_portfolio(rates=portfolio_rates), "sel-live-a"
    )
    text = budget_markdown(portfolio, selection, cost)
    assert "Benchmark" not in text


def test_markdown_benchmark_source_only(make_portfolio, portfolio_rates):
    portfolio_rates["roles"][0]["benchmark"] = {"source": "BLS OEWS"}
    portfolio, selection, cost = _compiled(
        make_portfolio(rates=portfolio_rates), "sel-live-a"
    )
    text = budget_markdown(portfolio, selection, cost)
    assert "| BLS OEWS |" in text
    assert ", p" not in text


def test_markdown_no_personnel_section_without_labor(
    make_portfolio, portfolio_selections
):
    # A units-only selection has no personnel: the section vanishes.
    selections = portfolio_selections + [_extra_selection("gamma-units")]
    portfolio, selection, cost = _compiled(
        make_portfolio(selections=selections), "sel-extra"
    )
    assert cost.personnel == {}
    text = budget_markdown(portfolio, selection, cost)
    assert "## Personnel" not in text
    assert "## Selected items" in text
    assert "## Category summary" in text


# -- narrative skeleton -------------------------------------------------


def test_narrative_excludes_zero_fraction_declarations(make_portfolio):
    # sel-draft declares beta at fraction 0: a declaration is not
    # narrated as funded work.
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-draft")
    text = budget_narrative(portfolio, selection, cost)
    assert "### Alpha coverage" in text
    assert "Beta platform" not in text


def test_narrative_partial_fraction_shows_share(make_portfolio):
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-draft")
    text = budget_narrative(portfolio, selection, cost)
    # 0.8 x 208,750 = 167,000, shown as a share of the full item cost.
    assert "USD 167,000 (80% of USD 208,750 at fraction 0.8)" in text


def test_narrative_full_fraction_shows_plain_cost(make_portfolio):
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-b")
    text = budget_narrative(portfolio, selection, cost)
    assert "### Delta hosting" in text
    assert "Cost: USD 60,000.\n" in text
    # The fully-funded line carries no fraction share clause; the
    # half-funded alpha line still does.
    assert "at fraction 0.5" in text
    assert "at fraction 1" not in text


def test_narrative_skips_lines_missing_from_menu(make_portfolio):
    # Defensive guard: a compiled line whose item id no longer resolves
    # is dropped from the narrative rather than crashing.
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-a")
    cost.items[0].item_id = "ghost"
    text = budget_narrative(portfolio, selection, cost)
    assert "Alpha coverage" not in text
    assert "Gamma evaluation" in text


def test_narrative_budget_justification_lists_roles(make_portfolio):
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-a")
    text = budget_narrative(portfolio, selection, cost)
    assert "## Budget justification" in text
    assert (
        "- Encoding Lead: 3 FTE-months at USD 320,000 fully loaded "
        "per year = USD 80,000." in text
    )
    assert "Benchmark: BLS OEWS May 2024" in text
    # Research Engineer has no benchmark: no trailing benchmark clause.
    assert "- Research Engineer: 1.5 FTE-months" in text


# -- rich tables --------------------------------------------------------


def _rich_output(portfolio, selection, cost):
    console = Console(file=io.StringIO(), width=120, force_terminal=False)
    print_budget(console, portfolio, selection, cost)
    return console.file.getvalue()


def test_print_budget_without_personnel_or_target(
    make_portfolio, portfolio_selections
):
    selections = portfolio_selections + [_extra_selection("gamma-units")]
    portfolio, selection, cost = _compiled(
        make_portfolio(selections=selections), "sel-extra"
    )
    out = _rich_output(portfolio, selection, cost)
    assert "no target" in out
    assert "Gamma evaluation" in out
    assert "FTE-months" not in out  # no personnel table
    assert "Target fit" not in out


def test_print_budget_personnel_without_benchmarks(
    make_portfolio, portfolio_selections
):
    # beta is costed with Program Lead only: the rich personnel table
    # renders without a Benchmark column.
    selections = portfolio_selections + [_extra_selection("beta")]
    portfolio, selection, cost = _compiled(
        make_portfolio(selections=selections), "sel-extra"
    )
    out = _rich_output(portfolio, selection, cost)
    assert "FTE-months" in out
    assert "Program Lead" in out
    assert "Benchmark" not in out


def test_print_budget_with_target_and_benchmarks(make_portfolio):
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-a")
    out = _rich_output(portfolio, selection, cost)
    assert "target USD 500,000" in out
    assert "Benchmark" in out
    assert "Target fit" in out
    assert "49%" in out


def test_markdown_is_pure_function_of_inputs(make_portfolio):
    portfolio, selection, cost = _compiled(make_portfolio(), "sel-live-a")
    first = budget_markdown(portfolio, selection, cost, narrative=True)
    second = budget_markdown(portfolio, selection, cost, narrative=True)
    assert first == second
    assert first.endswith("\n")


@pytest.mark.parametrize("value,expected", [(0.5, 1), (1.5, 2), (2.5, 3)])
def test_round_half_up_every_tie_goes_up(value, expected):
    assert round_half_up(value) == expected
