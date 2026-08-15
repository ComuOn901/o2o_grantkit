"""Tests for the budget-model document schemas."""

import pytest

from grantkit.menu import (
    Menu,
    Rates,
    Selection,
    validate_menu,
    validate_rates,
    validate_selection,
)

# -- menu.yaml ----------------------------------------------------------


def test_valid_menu_passes(portfolio_menu):
    assert validate_menu(portfolio_menu) == []


def test_menu_must_be_mapping():
    assert validate_menu(["not", "a", "dict"]) == [
        "menu must be a mapping/dict"
    ]


def test_menu_requires_schema_marker(portfolio_menu):
    portfolio_menu["schema"] = "grantkit-menu/v1"
    assert any("'schema'" in e for e in validate_menu(portfolio_menu))
    del portfolio_menu["schema"]
    assert any("'schema'" in e for e in validate_menu(portfolio_menu))


def test_menu_requires_currency(portfolio_menu):
    del portfolio_menu["currency"]
    assert any("currency" in e for e in validate_menu(portfolio_menu))


def test_menu_overheads_rate_range(portfolio_menu):
    portfolio_menu["overheads"]["fiscal_sponsorship_rate"] = 1.5
    assert any(
        "fiscal_sponsorship_rate" in e for e in validate_menu(portfolio_menu)
    )
    portfolio_menu["overheads"]["fiscal_sponsorship_rate"] = -0.1
    assert any(
        "fiscal_sponsorship_rate" in e for e in validate_menu(portfolio_menu)
    )
    portfolio_menu["overheads"] = "seven percent"
    assert any("overheads" in e for e in validate_menu(portfolio_menu))


def test_menu_unit_costs_require_price(portfolio_menu):
    del portfolio_menu["unit_costs"]["module"]["usd_per_unit"]
    assert any("usd_per_unit" in e for e in validate_menu(portfolio_menu))
    portfolio_menu["unit_costs"] = ["module"]
    assert any("unit_costs" in e for e in validate_menu(portfolio_menu))


def test_menu_items_must_be_list(portfolio_menu):
    portfolio_menu["items"] = "everything"
    assert any("'items'" in e for e in validate_menu(portfolio_menu))


def test_menu_item_id_pattern_and_uniqueness(portfolio_menu):
    portfolio_menu["items"][1]["id"] = "Alpha Coverage"
    errors = validate_menu(portfolio_menu)
    assert any("[a-z0-9-]+" in e for e in errors)
    portfolio_menu["items"][1]["id"] = "org-floor"
    errors = validate_menu(portfolio_menu)
    assert any("duplicate item id" in e for e in errors)
    del portfolio_menu["items"][1]["id"]
    assert any("missing 'id'" in e for e in validate_menu(portfolio_menu))


@pytest.mark.parametrize("key", ["type", "title", "what", "evidence"])
def test_menu_item_required_text_fields(portfolio_menu, key):
    del portfolio_menu["items"][1][key]
    assert any(f"missing '{key}'" in e for e in validate_menu(portfolio_menu))


def test_menu_item_status_vocabulary(portfolio_menu):
    portfolio_menu["items"][1]["status"] = "someday"
    assert any("invalid status" in e for e in validate_menu(portfolio_menu))


def test_menu_item_duration_must_be_int(portfolio_menu):
    portfolio_menu["items"][1]["duration_months"] = "nine"
    assert any("duration_months" in e for e in validate_menu(portfolio_menu))


def test_menu_item_dependencies_required_list(portfolio_menu):
    del portfolio_menu["items"][1]["dependencies"]
    assert any("dependencies" in e for e in validate_menu(portfolio_menu))


def test_menu_item_provenance_required_nonempty(portfolio_menu):
    portfolio_menu["items"][1]["provenance"] = []
    assert any("provenance" in e for e in validate_menu(portfolio_menu))


def test_menu_item_resourcing_required(portfolio_menu):
    del portfolio_menu["items"][1]["resourcing"]
    assert any("resourcing" in e for e in validate_menu(portfolio_menu))


def test_menu_item_resourcing_needs_a_costed_field(portfolio_menu):
    portfolio_menu["items"][1]["resourcing"] = {"overhead_included": True}
    assert any(
        "at least one costed field" in e for e in validate_menu(portfolio_menu)
    )


def test_menu_item_fte_months_non_negative(portfolio_menu):
    resourcing = portfolio_menu["items"][1]["resourcing"]
    resourcing["fte_months"]["Encoding Lead"] = -1
    assert any("fte_months" in e for e in validate_menu(portfolio_menu))
    resourcing["fte_months"] = "six"
    assert any("fte_months" in e for e in validate_menu(portfolio_menu))


def test_menu_item_units_non_negative(portfolio_menu):
    portfolio_menu["items"][3]["resourcing"]["units"]["module"] = -5
    assert any("units[" in e for e in validate_menu(portfolio_menu))


def test_menu_item_money_fields_numeric(portfolio_menu):
    portfolio_menu["items"][2]["resourcing"]["contract_usd"] = "lots"
    assert any("contract_usd" in e for e in validate_menu(portfolio_menu))


def test_menu_item_overhead_included_boolean(portfolio_menu):
    resourcing = portfolio_menu["items"][0]["resourcing"]
    resourcing["overhead_included"] = "yes"
    assert any("overhead_included" in e for e in validate_menu(portfolio_menu))


def test_menu_from_dict_survives_garbage():
    menu = Menu.from_dict(
        {"items": ["nope", {"resourcing": "flat"}], "unit_costs": 3}
    )
    assert menu.unit_costs == {}
    assert len(menu.items) == 1


# -- rates.yaml ---------------------------------------------------------


def test_valid_rates_pass(portfolio_rates):
    assert validate_rates(portfolio_rates) == []


def test_rates_must_be_mapping():
    assert validate_rates(None) == ["rates must be a mapping/dict"]


def test_rates_schema_marker(portfolio_rates):
    portfolio_rates["schema"] = "grantkit-rates/v9"
    assert any("'schema'" in e for e in validate_rates(portfolio_rates))


@pytest.mark.parametrize("key", ["provider", "generated", "currency"])
def test_rates_required_keys(portfolio_rates, key):
    del portfolio_rates[key]
    assert any(key in e for e in validate_rates(portfolio_rates))


def test_rates_generated_must_be_iso_date(portfolio_rates):
    portfolio_rates["generated"] = "August 15th"
    assert any("ISO date" in e for e in validate_rates(portfolio_rates))


def test_rates_roles_must_be_list(portfolio_rates):
    portfolio_rates["roles"] = {"Encoding Lead": 320000}
    assert any("'roles'" in e for e in validate_rates(portfolio_rates))


def test_rates_role_requires_name_and_loaded(portfolio_rates):
    del portfolio_rates["roles"][2]["role"]
    assert any("missing 'role'" in e for e in validate_rates(portfolio_rates))
    portfolio_rates["roles"][2]["role"] = "Program Lead"
    portfolio_rates["roles"][2]["loaded_usd"] = 0
    assert any("loaded_usd" in e for e in validate_rates(portfolio_rates))


def test_rates_duplicate_role(portfolio_rates):
    portfolio_rates["roles"][2]["role"] = "Encoding Lead"
    assert any("duplicate role" in e for e in validate_rates(portfolio_rates))


def test_rates_base_must_be_number(portfolio_rates):
    portfolio_rates["roles"][1]["base_usd"] = "150k"
    assert any("base_usd" in e for e in validate_rates(portfolio_rates))


def test_rates_component_basis_vocabulary(portfolio_rates):
    component = portfolio_rates["roles"][0]["components"][0]
    component["basis"] = "vibes"
    assert any("invalid basis" in e for e in validate_rates(portfolio_rates))
    del component["basis"]
    assert any("invalid basis" in e for e in validate_rates(portfolio_rates))


def test_rates_component_requires_name_and_amount(portfolio_rates):
    component = portfolio_rates["roles"][0]["components"][0]
    del component["name"]
    del component["amount_usd"]
    errors = validate_rates(portfolio_rates)
    assert any("missing 'name'" in e for e in errors)
    assert any("amount_usd" in e for e in errors)


def test_rates_benchmark_types(portfolio_rates):
    portfolio_rates["roles"][0]["benchmark"] = "BLS"
    assert any("'benchmark'" in e for e in validate_rates(portfolio_rates))
    portfolio_rates["roles"][0]["benchmark"] = {"percentile": "high"}
    assert any(
        "benchmark.percentile" in e for e in validate_rates(portfolio_rates)
    )


def test_rates_provenance_must_be_list(portfolio_rates):
    portfolio_rates["roles"][0]["provenance"] = "synthetic"
    assert any("'provenance'" in e for e in validate_rates(portfolio_rates))


def test_rates_from_dict_survives_garbage():
    rates = Rates.from_dict({"roles": [None, {"components": "x"}]})
    assert len(rates.roles) == 1
    assert rates.roles[0].components == []


# -- selection.yaml -----------------------------------------------------


def _selection(portfolio_selections):
    return portfolio_selections[0]


def test_valid_selections_pass(portfolio_selections):
    for selection in portfolio_selections:
        assert validate_selection(selection) == []


def test_selection_must_be_mapping():
    assert validate_selection(7) == ["selection must be a mapping/dict"]


def test_selection_schema_marker(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["schema"] = "grantkit-menu/v0"
    assert any("'schema'" in e for e in validate_selection(selection))


@pytest.mark.parametrize("key", ["id", "funder"])
def test_selection_required_keys(portfolio_selections, key):
    selection = _selection(portfolio_selections)
    del selection[key]
    assert any(key in e for e in validate_selection(selection))


def test_selection_status_vocabulary(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["status"] = "maybe"
    assert any("invalid status" in e for e in validate_selection(selection))


def test_selection_target_must_be_number(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["target_usd"] = "2M"
    assert any("target_usd" in e for e in validate_selection(selection))


@pytest.mark.parametrize("window", [None, 0, -3, 2.5, True])
def test_selection_window_months_positive_int(portfolio_selections, window):
    selection = _selection(portfolio_selections)
    selection["window_months"] = window
    assert any("window_months" in e for e in validate_selection(selection))


def test_selection_org_base_shape(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["org_base"] = {"fraction": 0.1}
    assert any(
        "org_base missing 'item'" in e for e in validate_selection(selection)
    )
    selection["org_base"] = {"item": "org-floor"}
    assert any("'fraction'" in e for e in validate_selection(selection))
    selection["org_base"] = "org-floor"
    assert any("org_base" in e for e in validate_selection(selection))


def test_selection_lines_shape(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["selections"] = "alpha"
    assert any("'selections'" in e for e in validate_selection(selection))
    selection["selections"] = [{"fraction": 0.5}]
    assert any("missing 'item'" in e for e in validate_selection(selection))
    selection["selections"] = [{"item": "alpha"}]
    assert any("'fraction'" in e for e in validate_selection(selection))
    selection["selections"] = [{"item": "alpha", "fraction": "half"}]
    assert any("'fraction'" in e for e in validate_selection(selection))


def test_selection_from_dict_preserves_explicit_zero(
    portfolio_selections,
):
    selection = Selection.from_dict(portfolio_selections[2])
    fractions = {line.item: line.fraction for line in selection.selections}
    assert fractions["beta"] == 0.0
    assert selection.selections[1].note == "declared, not billed here"
