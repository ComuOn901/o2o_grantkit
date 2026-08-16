"""Tests for the portfolio integrity gates (including the C2 gate)."""

import pytest

from grantkit.menu import load_portfolio, run_gates
from grantkit.packs.schema import BudgetRules, FunderPack


def _gates(root, selection_id=None, pack=None):
    return run_gates(load_portfolio(root), selection_id, pack)


def _rules(items):
    return {item.rule for item in items}


def _by_rule(items, rule):
    return [item for item in items if item.rule == rule]


def _pack(**budget_rules):
    return FunderPack(
        id="test-pack",
        name="Test Pack",
        budget_rules=BudgetRules(**budget_rules),
    )


# -- clean portfolio ----------------------------------------------------


def test_default_portfolio_is_clean(make_portfolio):
    assert _gates(make_portfolio()) == []


def test_cofunding_boundary_exactly_one_passes(make_portfolio):
    # alpha is funded 0.5 + 0.5 across the two live selections — the
    # sum is exactly 1.0 and must not trip the gate.
    items = _gates(make_portfolio())
    assert _by_rule(items, "cofunding_over_allocated") == []


# -- the C2 co-funding gate ---------------------------------------------


def test_cofunding_over_allocation_fails(make_portfolio, portfolio_selections):
    portfolio_selections[1]["selections"][0]["fraction"] = 0.6
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "cofunding_over_allocated")
    assert len(hits) == 1
    assert hits[0].level == "error"
    assert "alpha" in hits[0].message
    assert "sel-live-a" in hits[0].message
    assert "sel-live-b" in hits[0].message


def test_cofunding_message_preserves_tolerance_scale(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["selections"][0]["fraction"] = 0.5000000006
    portfolio_selections[1]["selections"][0]["fraction"] = 0.5000000006
    items = _gates(make_portfolio(selections=portfolio_selections))
    message = _by_rule(items, "cofunding_over_allocated")[0].message
    assert "0.5000000006 +" in message
    assert "1.0000000012" in message


def test_cofunding_ignores_drafts(make_portfolio, portfolio_selections):
    # The draft over-planner takes 0.8 of alpha on top of the two live
    # halves; drafts are free to over-plan.
    portfolio_selections[2]["selections"][0]["fraction"] = 0.8
    items = _gates(make_portfolio(selections=portfolio_selections))
    assert _by_rule(items, "cofunding_over_allocated") == []


def test_cofunding_awarded_counts_as_live(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["status"] = "awarded"
    portfolio_selections[1]["selections"][0]["fraction"] = 0.6
    items = _gates(make_portfolio(selections=portfolio_selections))
    assert len(_by_rule(items, "cofunding_over_allocated")) == 1


@pytest.mark.parametrize("status", ["withdrawn", "declined"])
def test_cofunding_excludes_dead_selections(
    make_portfolio, portfolio_selections, status
):
    portfolio_selections[1]["status"] = status
    portfolio_selections[1]["selections"][0]["fraction"] = 0.9
    items = _gates(make_portfolio(selections=portfolio_selections))
    assert _by_rule(items, "cofunding_over_allocated") == []


def test_cofunding_applies_to_org_base_fractions(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["org_base"] = {
        "item": "org-floor",
        "fraction": 0.95,
    }
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "cofunding_over_allocated")
    assert len(hits) == 1
    assert "org-floor" in hits[0].message
    assert "org base" in hits[0].message


def test_cofunding_sums_org_base_and_line_claims(
    make_portfolio, portfolio_selections
):
    # One selection claims org-floor as its org base (0.6), another
    # sells it as a plain line (0.6): the same item is over-allocated
    # across kinds, and the message tags which claim is the org base.
    portfolio_selections[0]["org_base"]["fraction"] = 0.6
    portfolio_selections[1]["selections"].append(
        {"item": "org-floor", "fraction": 0.6}
    )
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "cofunding_over_allocated")
    assert len(hits) == 1
    assert "org-floor" in hits[0].message
    assert "sel-live-a (org base) 0.6" in hits[0].message
    assert "sel-live-b 0.6" in hits[0].message


# -- referential gates --------------------------------------------------


def test_unknown_item_in_selection(make_portfolio, portfolio_selections):
    portfolio_selections[0]["selections"].append(
        {"item": "zzz", "fraction": 0.1}
    )
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "unknown_item")
    assert hits and all(item.level == "error" for item in hits)
    assert hits[0].section == "sel-live-a"


def test_unknown_item_in_org_base(make_portfolio, portfolio_selections):
    portfolio_selections[0]["org_base"]["item"] = "zzz"
    items = _gates(make_portfolio(selections=portfolio_selections))
    assert _by_rule(items, "unknown_item")


def test_unknown_role(make_portfolio, portfolio_menu):
    resourcing = portfolio_menu["items"][1]["resourcing"]
    resourcing["fte_months"]["Chief Vibes Officer"] = 2
    items = _gates(make_portfolio(menu=portfolio_menu))
    hits = _by_rule(items, "unknown_role")
    assert len(hits) == 1
    assert "Chief Vibes Officer" in hits[0].message
    assert "eggnest-employer 0.2.0" in hits[0].message


def test_unknown_unit(make_portfolio, portfolio_menu):
    portfolio_menu["items"][3]["resourcing"]["units"]["widget"] = 5
    items = _gates(make_portfolio(menu=portfolio_menu))
    assert len(_by_rule(items, "unknown_unit")) == 1


def test_dependency_unresolved(make_portfolio, portfolio_menu):
    portfolio_menu["items"][1]["dependencies"] = ["zzz"]
    items = _gates(make_portfolio(menu=portfolio_menu))
    hits = _by_rule(items, "dependency_unresolved")
    assert len(hits) == 1
    assert "'zzz'" in hits[0].message


def test_dependency_cycle(make_portfolio, portfolio_menu):
    portfolio_menu["items"][2]["dependencies"] = ["alpha"]
    items = _gates(make_portfolio(menu=portfolio_menu))
    hits = _by_rule(items, "dependency_cycle")
    assert len(hits) == 1  # one cycle, reported once
    assert "alpha" in hits[0].message and "beta" in hits[0].message


def test_dependency_self_cycle(make_portfolio, portfolio_menu):
    portfolio_menu["items"][1]["dependencies"] = ["alpha"]
    items = _gates(make_portfolio(menu=portfolio_menu))
    hits = _by_rule(items, "dependency_cycle")
    assert len(hits) == 1
    assert "alpha -> alpha" in hits[0].message


def test_dependency_cycle_reported_once_despite_duplicate_deps(
    make_portfolio, portfolio_menu
):
    # beta lists alpha twice; the alpha <-> beta cycle is still one
    # finding, not one per traversal.
    portfolio_menu["items"][2]["dependencies"] = ["alpha", "alpha"]
    items = _gates(make_portfolio(menu=portfolio_menu))
    assert len(_by_rule(items, "dependency_cycle")) == 1


def test_dependency_cycle_handles_deep_graph_iteratively(
    make_portfolio, portfolio_menu
):
    count = 1200
    portfolio_menu["items"] = [
        {
            "id": f"node-{index:04d}",
            "type": "platform",
            "title": f"Node {index}",
            "what": "A synthetic dependency node.",
            "evidence": "Node completed.",
            "status": "planned",
            "dependencies": [
                f"node-{index + 1:04d}" if index + 1 < count else "node-0000"
            ],
            "provenance": ["synthetic"],
            "resourcing": {"amount_usd": 1},
        }
        for index in range(count)
    ]
    items = _gates(make_portfolio(menu=portfolio_menu, selections=[]))
    assert len(_by_rule(items, "dependency_cycle")) == 1


def test_unnamed_selection_reported_with_placeholder(
    make_portfolio, portfolio_selections
):
    del portfolio_selections[0]["id"]
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "selection_invalid")
    assert any("(unnamed)" in item.message for item in hits)


def test_fraction_out_of_range(make_portfolio, portfolio_selections):
    portfolio_selections[0]["selections"][0]["fraction"] = 1.5
    portfolio_selections[1]["selections"][0]["fraction"] = -0.1
    portfolio_selections[0]["org_base"]["fraction"] = 1.2
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "fraction_out_of_range")
    assert len(hits) == 3
    assert all(item.level == "error" for item in hits)


def test_fraction_range_message_does_not_round_violation_away(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["selections"][0]["fraction"] = 1.0000000001
    items = _gates(make_portfolio(selections=portfolio_selections))
    message = _by_rule(items, "fraction_out_of_range")[0].message
    assert "1.0000000001" in message


def test_scoped_gates_validate_out_of_scope_binding_fractions(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["selections"][0]["fraction"] = -0.5
    portfolio_selections[1]["selections"][0]["fraction"] = 1.0
    items = _gates(
        make_portfolio(selections=portfolio_selections),
        selection_id="sel-live-b",
    )
    hits = _by_rule(items, "fraction_out_of_range")
    assert len(hits) == 1
    assert hits[0].section == "sel-live-a"


def test_org_base_type(make_portfolio, portfolio_selections):
    portfolio_selections[0]["org_base"]["item"] = "alpha"
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "org_base_type")
    assert len(hits) == 1
    assert "program-coverage" in hits[0].message


def test_selection_duplicate_item(make_portfolio, portfolio_selections):
    portfolio_selections[0]["selections"].append(
        {"item": "alpha", "fraction": 0.2}
    )
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "selection_duplicate_item")
    assert len(hits) == 1
    assert "sel-live-a" in hits[0].message


def test_explicit_zero_fraction_is_not_a_duplicate(make_portfolio):
    # sel-draft declares beta at fraction 0 alongside funded lines;
    # a declaration is one line, not a duplicate.
    items = _gates(make_portfolio())
    assert _by_rule(items, "selection_duplicate_item") == []


# -- advisory warnings --------------------------------------------------


def test_dependency_unfunded_warns(
    make_portfolio, portfolio_menu, portfolio_selections
):
    # beta becomes planned and nothing live funds it -> funding alpha
    # assumes work nobody has funded.
    portfolio_menu["items"][2]["status"] = "planned"
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    )
    hits = _by_rule(items, "dependency_unfunded")
    assert hits and all(item.level == "warning" for item in hits)
    assert any("'beta'" in item.message for item in hits)


def test_dependency_funded_in_live_selection_is_covered(
    make_portfolio, portfolio_menu, portfolio_selections
):
    portfolio_menu["items"][2]["status"] = "planned"
    portfolio_selections[1]["selections"].append(
        {"item": "beta", "fraction": 0.3}
    )
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    )
    assert _by_rule(items, "dependency_unfunded") == []


def test_dependency_funded_as_org_base_is_covered(
    make_portfolio, portfolio_menu, portfolio_selections
):
    portfolio_menu["items"][0]["status"] = "planned"
    portfolio_menu["items"][1]["dependencies"] = ["org-floor"]
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    )
    assert _by_rule(items, "dependency_unfunded") == []


def test_org_base_claim_checks_its_own_dependencies(
    make_portfolio, portfolio_menu, portfolio_selections
):
    portfolio_menu["items"][0]["status"] = "planned"
    portfolio_menu["items"][0]["dependencies"] = ["beta"]
    portfolio_menu["items"][1]["dependencies"] = []
    portfolio_menu["items"][2]["status"] = "planned"
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections),
        selection_id="sel-live-a",
    )
    hits = _by_rule(items, "dependency_unfunded")
    assert len(hits) == 1
    assert "'org-floor'" in hits[0].message
    assert "'beta'" in hits[0].message


def test_dependency_self_funded_is_covered(
    make_portfolio, portfolio_menu, portfolio_selections
):
    # The draft funds both alpha and its planned dependency beta, so
    # gating the draft alone raises no unfunded-dependency warning.
    portfolio_menu["items"][2]["status"] = "planned"
    portfolio_selections[2]["selections"][1]["fraction"] = 0.5
    root = make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    items = _gates(root, selection_id="sel-draft")
    assert _by_rule(items, "dependency_unfunded") == []


def test_shipped_dependency_is_covered(make_portfolio, portfolio_menu):
    portfolio_menu["items"][1]["dependencies"] = ["shipped-item"]
    items = _gates(make_portfolio(menu=portfolio_menu))
    assert _by_rule(items, "dependency_unfunded") == []


def test_in_flight_dependency_is_covered(make_portfolio):
    # beta (alpha's dependency) is in-flight in the default menu: work
    # already underway needs no new funder.
    items = _gates(make_portfolio())
    assert _by_rule(items, "dependency_unfunded") == []


def test_dependency_funded_only_in_draft_still_warns(
    make_portfolio, portfolio_menu, portfolio_selections
):
    # The draft funds beta, but a draft's funding is not real funding:
    # the live selections still assume work nobody has funded. The
    # draft itself self-funds beta, so it is not warned.
    portfolio_menu["items"][2]["status"] = "planned"
    portfolio_selections[2]["selections"][1]["fraction"] = 0.5
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    )
    hits = _by_rule(items, "dependency_unfunded")
    assert {item.section for item in hits} == {"sel-live-a", "sel-live-b"}


def test_dependency_funded_in_awarded_selection_is_covered(
    make_portfolio, portfolio_menu, portfolio_selections
):
    portfolio_menu["items"][2]["status"] = "planned"
    portfolio_selections[1]["status"] = "awarded"
    portfolio_selections[1]["selections"].append(
        {"item": "beta", "fraction": 0.3}
    )
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=portfolio_selections)
    )
    assert _by_rule(items, "dependency_unfunded") == []


def test_zero_fraction_line_skips_dependency_warning(
    make_portfolio, portfolio_menu, portfolio_selections
):
    # A lone draft declares alpha at fraction 0 while beta is planned
    # and unfunded: a declaration assumes nothing, so no warning.
    portfolio_menu["items"][2]["status"] = "planned"
    draft = portfolio_selections[2]
    draft["selections"][0]["fraction"] = 0.0
    items = _gates(make_portfolio(menu=portfolio_menu, selections=[draft]))
    assert _by_rule(items, "dependency_unfunded") == []


def test_over_target_warning(make_portfolio, portfolio_selections):
    portfolio_selections[0]["target_usd"] = 100000
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "over_target")
    assert len(hits) == 1
    assert hits[0].level == "warning"
    assert "ask, not a funder cap" in hits[0].message


def test_gate_money_uses_half_up_rounding(
    make_portfolio, portfolio_menu, portfolio_selections
):
    portfolio_menu["overheads"]["fiscal_sponsorship_rate"] = 0
    portfolio_menu["items"][3]["resourcing"]["units"]["module"] = 1
    selection = portfolio_selections[0]
    selection["target_usd"] = 2
    selection.pop("org_base")
    selection["selections"] = [{"item": "gamma-units", "fraction": 1.0}]
    items = _gates(
        make_portfolio(menu=portfolio_menu, selections=[selection]),
        selection_id="sel-live-a",
        pack=_pack(total_cap=2),
    )
    assert "USD 3" in _by_rule(items, "over_target")[0].message
    assert "USD 3" in _by_rule(items, "budget_over_total_cap")[0].message


def test_derived_non_finite_total_is_an_error(make_portfolio, portfolio_menu):
    portfolio_menu["unit_costs"]["module"]["usd_per_unit"] = 1e308
    portfolio_menu["items"][3]["resourcing"]["units"]["module"] = 1e308
    items = _gates(make_portfolio(menu=portfolio_menu))
    hits = _by_rule(items, "budget_non_finite")
    assert hits and all(item.level == "error" for item in hits)


def test_derived_non_finite_fit_is_an_error(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["target_usd"] = 5e-324
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "budget_non_finite")
    assert len(hits) == 1
    assert hits[0].section == "sel-live-a"


def test_zero_target_does_not_divide_by_zero(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["target_usd"] = 0
    items = _gates(make_portfolio(selections=portfolio_selections))
    assert _by_rule(items, "over_target") == []


def test_load_factor_suspicious_low_and_high(make_portfolio, portfolio_rates):
    portfolio_rates["roles"][1]["loaded_usd"] = 150000  # equals base
    portfolio_rates["roles"][0]["loaded_usd"] = 700000  # 2.9x base
    del portfolio_rates["roles"][0]["components"]
    items = _gates(make_portfolio(rates=portfolio_rates))
    hits = _by_rule(items, "load_factor_suspicious")
    assert len(hits) == 2
    assert all(item.level == "warning" for item in hits)
    assert any("pasted base as loaded" in item.message for item in hits)


def test_components_mismatch_warns(make_portfolio, portfolio_rates):
    portfolio_rates["roles"][0]["components"][0]["amount_usd"] = 5000
    items = _gates(make_portfolio(rates=portfolio_rates))
    hits = _by_rule(items, "components_mismatch")
    assert len(hits) == 1
    assert hits[0].level == "warning"


def test_rate_heuristics_handle_finite_operands_with_huge_ratio(
    make_portfolio, portfolio_rates
):
    portfolio_rates["roles"][1]["base_usd"] = 5e-324
    portfolio_rates["roles"][1]["loaded_usd"] = 1e308
    items = _gates(make_portfolio(rates=portfolio_rates))
    hits = _by_rule(items, "load_factor_suspicious")
    assert len(hits) == 1
    assert "finite float range" in hits[0].message


def test_loaded_only_role_raises_no_heuristics(make_portfolio):
    # Program Lead has no base_usd: the load-factor and component
    # heuristics need a base, so a loaded-only role is silent.
    items = _gates(make_portfolio())
    assert _by_rule(items, "load_factor_suspicious") == []


def test_load_factor_band_boundaries_are_inclusive(
    make_portfolio, portfolio_rates
):
    # Exactly 1.05 and exactly 2.0 sit inside the advisory band.
    portfolio_rates["roles"][1].update(base_usd=200000, loaded_usd=210000)
    portfolio_rates["roles"][2].update(base_usd=150000, loaded_usd=300000)
    items = _gates(make_portfolio(rates=portfolio_rates))
    assert _by_rule(items, "load_factor_suspicious") == []


def test_components_tolerance_is_one_dollar(make_portfolio, portfolio_rates):
    # Components sum to 320,000; loaded off by exactly $1 stays silent,
    # $2 warns.
    portfolio_rates["roles"][0]["loaded_usd"] = 320001
    items = _gates(make_portfolio(rates=portfolio_rates))
    assert _by_rule(items, "components_mismatch") == []
    portfolio_rates["roles"][0]["loaded_usd"] = 320002
    items = _gates(make_portfolio(rates=portfolio_rates))
    assert len(_by_rule(items, "components_mismatch")) == 1


# -- schema gating and scoping ------------------------------------------


def test_portfolio_without_selections_is_clean(make_portfolio):
    assert _gates(make_portfolio(selections=[])) == []


def test_rates_schema_errors_surface_as_rates_invalid(
    make_portfolio, portfolio_rates
):
    portfolio_rates["generated"] = "August 15th"
    items = _gates(make_portfolio(rates=portfolio_rates))
    assert items
    assert _rules(items) == {"rates_invalid"}
    assert all(item.level == "error" for item in items)


def test_schema_errors_short_circuit(make_portfolio, portfolio_menu):
    del portfolio_menu["currency"]
    portfolio_menu["items"][1]["resourcing"]["fte_months"][
        "Nobody"
    ] = 1  # would be unknown_role, but schema errors come first
    items = _gates(make_portfolio(menu=portfolio_menu))
    assert items
    assert _rules(items) == {"menu_invalid"}


def test_currency_mismatch_is_an_error(make_portfolio, portfolio_rates):
    portfolio_rates["currency"] = "EUR"
    items = _gates(make_portfolio(rates=portfolio_rates))
    hits = _by_rule(items, "rates_invalid")
    assert len(hits) == 1
    assert "EUR" in hits[0].message and "USD" in hits[0].message


def test_duplicate_selection_ids(make_portfolio, portfolio_selections):
    duplicate = dict(portfolio_selections[0])
    root = make_portfolio(
        selections=portfolio_selections, single_selection=duplicate
    )
    items = _gates(root)
    assert any(
        "duplicate selection id" in item.message
        for item in _by_rule(items, "selection_invalid")
    )


def test_selection_invalid_reports_schema_errors(
    make_portfolio, portfolio_selections
):
    del portfolio_selections[0]["funder"]
    items = _gates(make_portfolio(selections=portfolio_selections))
    hits = _by_rule(items, "selection_invalid")
    assert hits and hits[0].section == "sel-live-a"


def test_selection_id_scopes_per_selection_gates(
    make_portfolio, portfolio_selections
):
    portfolio_selections[2]["selections"].append(
        {"item": "zzz", "fraction": 0.1}
    )
    root = make_portfolio(selections=portfolio_selections)
    scoped = _gates(root, selection_id="sel-live-a")
    assert _by_rule(scoped, "unknown_item") == []
    unscoped = _gates(root)
    assert _by_rule(unscoped, "unknown_item")


def test_unknown_selection_id_is_an_error(make_portfolio):
    items = _gates(make_portfolio(), selection_id="ghost")
    hits = _by_rule(items, "unknown_selection")
    assert len(hits) == 1
    assert hits[0].level == "error"
    assert "sel-live-a" in hits[0].message


# -- pack caps ----------------------------------------------------------


def test_pack_total_cap_is_an_error(make_portfolio):
    items = _gates(
        make_portfolio(),
        selection_id="sel-live-a",
        pack=_pack(total_cap=200000),
    )
    hits = _by_rule(items, "budget_over_total_cap")
    assert len(hits) == 1
    assert hits[0].level == "error"
    assert "245,056" in hits[0].message


def test_pack_annual_cap_is_a_warning(make_portfolio):
    items = _gates(
        make_portfolio(),
        selection_id="sel-live-a",
        pack=_pack(annual_cap=100000),
    )
    hits = _by_rule(items, "budget_over_annual_cap")
    assert len(hits) == 1
    assert hits[0].level == "warning"
    assert "approximation" in hits[0].message


def test_pack_caps_pass_when_under(make_portfolio):
    items = _gates(
        make_portfolio(),
        selection_id="sel-live-a",
        pack=_pack(total_cap=2000000, annual_cap=2000000),
    )
    assert items == []


def test_pack_caps_reject_currency_mismatch(make_portfolio):
    items = _gates(
        make_portfolio(),
        selection_id="sel-live-a",
        pack=_pack(currency="GBP", total_cap=200000),
    )
    hits = _by_rule(items, "budget_currency_mismatch")
    assert len(hits) == 1
    assert hits[0].level == "error"
    assert "USD" in hits[0].message and "GBP" in hits[0].message
    assert _by_rule(items, "budget_over_total_cap") == []
