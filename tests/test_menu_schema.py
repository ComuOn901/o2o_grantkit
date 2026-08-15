"""Tests for the budget-model document schemas."""

from copy import deepcopy

import pytest

from grantkit.menu import (
    Menu,
    Rates,
    Selection,
    validate_menu,
    validate_rates,
    validate_selection,
)


def _set_path(data, path, value):
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


NON_FINITE = [
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


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


def test_menu_item_status_wrong_shape_is_an_error(portfolio_menu):
    portfolio_menu["items"][1]["status"] = []
    assert any("invalid status" in e for e in validate_menu(portfolio_menu))


@pytest.mark.parametrize(
    "path",
    [
        ("overheads", "provenance"),
        ("unit_costs", "module", "derivation"),
        ("items", 1, "type"),
        ("items", 1, "revenue_unlock"),
    ],
    ids=("overhead-provenance", "unit-derivation", "type", "revenue"),
)
def test_menu_known_text_fields_reject_non_strings(portfolio_menu, path):
    _set_path(portfolio_menu, path, ["not", "text"])
    assert validate_menu(portfolio_menu)


@pytest.mark.parametrize("value", ["\ud800", "\x1b[31m", "\x00"])
def test_menu_text_fields_reject_unsafe_unicode(portfolio_menu, value):
    portfolio_menu["items"][1]["title"] = value
    assert any("title" in error for error in validate_menu(portfolio_menu))


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("unit_costs", "module", "provenance"), [1]),
        (("items", 1, "dependencies"), [123]),
        (("items", 1, "provenance"), [""]),
    ],
    ids=("unit-provenance", "dependencies", "item-provenance"),
)
def test_menu_string_lists_validate_entries(portfolio_menu, path, value):
    _set_path(portfolio_menu, path, value)
    assert validate_menu(portfolio_menu)


def test_menu_resourcing_and_unit_keys_must_be_strings(portfolio_menu):
    portfolio_menu["unit_costs"][1] = {
        "usd_per_unit": 2.5,
    }
    portfolio_menu["items"][1]["resourcing"]["fte_months"][1] = 2
    portfolio_menu["items"][3]["resourcing"]["units"][2] = 3
    errors = validate_menu(portfolio_menu)
    assert any("unit_costs keys" in error for error in errors)
    assert any("fte_months' keys" in error for error in errors)
    assert any("units' keys" in error for error in errors)


def test_menu_item_duration_must_be_int(portfolio_menu):
    portfolio_menu["items"][1]["duration_months"] = "nine"
    assert any("duration_months" in e for e in validate_menu(portfolio_menu))


def test_menu_item_duration_bool_rejected(portfolio_menu):
    # YAML `duration_months: true` is a bool, not an int.
    portfolio_menu["items"][1]["duration_months"] = True
    assert any("duration_months" in e for e in validate_menu(portfolio_menu))


def test_menu_item_duration_must_fit_numeric_model(portfolio_menu):
    portfolio_menu["items"][1]["duration_months"] = 10**10000
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


@pytest.mark.parametrize(
    "path",
    [
        ("unit_costs", "module", "usd_per_unit"),
        ("items", 0, "resourcing", "amount_usd"),
        ("items", 2, "resourcing", "contract_usd"),
        ("items", 4, "resourcing", "recurring_usd_per_year"),
    ],
    ids=("unit-price", "flat", "contract", "recurring"),
)
def test_menu_money_fields_must_be_non_negative(portfolio_menu, path):
    _set_path(portfolio_menu, path, -0.01)
    assert any("non-negative" in e for e in validate_menu(portfolio_menu))


@pytest.mark.parametrize("value", NON_FINITE)
@pytest.mark.parametrize(
    "path",
    [
        ("overheads", "fiscal_sponsorship_rate"),
        ("unit_costs", "module", "usd_per_unit"),
        ("items", 1, "resourcing", "fte_months", "Encoding Lead"),
        ("items", 3, "resourcing", "units", "module"),
        ("items", 2, "resourcing", "contract_usd"),
        ("items", 4, "resourcing", "recurring_usd_per_year"),
        ("items", 0, "resourcing", "amount_usd"),
    ],
    ids=(
        "overhead-rate",
        "unit-price",
        "fte-months",
        "unit-count",
        "contract",
        "recurring",
        "flat",
    ),
)
def test_menu_numeric_fields_must_be_finite(portfolio_menu, path, value):
    data = deepcopy(portfolio_menu)
    _set_path(data, path, value)
    assert validate_menu(data)


def test_menu_item_overhead_included_boolean(portfolio_menu):
    resourcing = portfolio_menu["items"][0]["resourcing"]
    resourcing["overhead_included"] = "yes"
    assert any("overhead_included" in e for e in validate_menu(portfolio_menu))


def test_menu_units_must_be_mapping(portfolio_menu):
    portfolio_menu["items"][3]["resourcing"]["units"] = ["module"]
    assert any(
        "'units' must be a mapping" in e for e in validate_menu(portfolio_menu)
    )


def test_menu_unit_cost_entry_must_be_mapping(portfolio_menu):
    portfolio_menu["unit_costs"]["module"] = 2.5
    assert any(
        "unit_costs['module'] must be a mapping" in e
        for e in validate_menu(portfolio_menu)
    )


def test_menu_unit_cost_provenance_must_be_list(portfolio_menu):
    portfolio_menu["unit_costs"]["module"]["provenance"] = "synthetic"
    assert any(
        "'provenance' must be a list" in e
        for e in validate_menu(portfolio_menu)
    )


def test_menu_item_entry_must_be_mapping(portfolio_menu):
    portfolio_menu["items"].append("alpha")
    assert any(
        "items[6] must be a mapping" in e
        for e in validate_menu(portfolio_menu)
    )


def test_menu_get_item_lookup(portfolio_menu):
    menu = Menu.from_dict(portfolio_menu)
    item = menu.get_item("alpha")
    assert item is not None and item.title == "Alpha coverage"
    assert menu.get_item("ghost") is None


def test_menu_from_dict_survives_garbage():
    menu = Menu.from_dict(
        {"items": ["nope", {"resourcing": "flat"}], "unit_costs": 3}
    )
    assert menu.unit_costs == {}
    assert len(menu.items) == 1


def test_menu_from_dict_skips_non_dict_unit_costs():
    menu = Menu.from_dict(
        {"unit_costs": {"module": 2.5, "ok": {"usd_per_unit": 1}}}
    )
    assert list(menu.unit_costs) == ["ok"]


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


def test_rates_component_basis_wrong_shape_is_an_error(portfolio_rates):
    portfolio_rates["roles"][0]["components"][0]["basis"] = []
    assert any("invalid basis" in e for e in validate_rates(portfolio_rates))


def test_rates_component_amount_must_be_non_negative(portfolio_rates):
    portfolio_rates["roles"][0]["components"][0]["amount_usd"] = -0.01
    errors = validate_rates(portfolio_rates)
    assert any(
        "amount_usd" in error and "non-negative" in error for error in errors
    )


@pytest.mark.parametrize(
    "path",
    [
        ("scenario",),
        ("jurisdiction",),
        ("method",),
        ("roles", 0, "soc"),
        ("roles", 0, "components", 0, "name"),
        ("roles", 0, "components", 0, "source"),
        ("roles", 0, "benchmark", "source"),
    ],
    ids=(
        "scenario",
        "jurisdiction",
        "method",
        "soc",
        "component-name",
        "component-source",
        "benchmark-source",
    ),
)
def test_rates_known_text_fields_reject_non_strings(portfolio_rates, path):
    _set_path(portfolio_rates, path, ["not", "text"])
    assert validate_rates(portfolio_rates)


def test_rates_text_fields_reject_lone_unicode_surrogates(portfolio_rates):
    portfolio_rates["provider"] = "\ud800"
    assert any(
        "provider" in error for error in validate_rates(portfolio_rates)
    )


def test_rates_provenance_entries_must_be_strings(portfolio_rates):
    portfolio_rates["roles"][0]["provenance"] = [123]
    assert any("provenance" in e for e in validate_rates(portfolio_rates))


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


@pytest.mark.parametrize("value", NON_FINITE)
@pytest.mark.parametrize(
    "path",
    [
        ("roles", 0, "loaded_usd"),
        ("roles", 0, "base_usd"),
        ("roles", 0, "components", 0, "amount_usd"),
        ("roles", 0, "benchmark", "percentile"),
        ("roles", 0, "benchmark", "value_usd"),
    ],
    ids=("loaded", "base", "component", "percentile", "benchmark-value"),
)
def test_rates_numeric_fields_must_be_finite(portfolio_rates, path, value):
    data = deepcopy(portfolio_rates)
    _set_path(data, path, value)
    assert validate_rates(data)


def test_rates_provenance_must_be_list(portfolio_rates):
    portfolio_rates["roles"][0]["provenance"] = "synthetic"
    assert any("'provenance'" in e for e in validate_rates(portfolio_rates))


def test_rates_role_entry_must_be_mapping(portfolio_rates):
    portfolio_rates["roles"].append("freelancer")
    assert any(
        "roles[3] must be a mapping" in e
        for e in validate_rates(portfolio_rates)
    )


def test_rates_components_must_be_list(portfolio_rates):
    portfolio_rates["roles"][0]["components"] = {"employer_taxes": 18000}
    assert any(
        "'components' must be a list" in e
        for e in validate_rates(portfolio_rates)
    )


def test_rates_component_entry_must_be_mapping(portfolio_rates):
    portfolio_rates["roles"][0]["components"][0] = "employer taxes"
    assert any(
        "components[0] must be a mapping" in e
        for e in validate_rates(portfolio_rates)
    )


def test_rates_get_role_lookup(portfolio_rates):
    rates = Rates.from_dict(portfolio_rates)
    role = rates.get_role("Program Lead")
    assert role is not None and role.loaded_usd == 180000
    assert rates.get_role("Ghost") is None


def test_rates_from_dict_survives_garbage():
    rates = Rates.from_dict({"roles": [None, {"components": "x"}]})
    assert len(rates.roles) == 1
    assert rates.roles[0].components == []


def test_rates_from_dict_skips_non_dict_components(portfolio_rates):
    portfolio_rates["roles"][0]["components"] = [
        "cash",
        {"name": "benefits", "amount_usd": 1, "basis": "assumed"},
    ]
    rates = Rates.from_dict(portfolio_rates)
    role = rates.get_role("Encoding Lead")
    assert [comp.name for comp in role.components] == ["benefits"]


def test_rates_from_dict_drops_non_mapping_benchmark(portfolio_rates):
    portfolio_rates["roles"][0]["benchmark"] = "BLS"
    rates = Rates.from_dict(portfolio_rates)
    assert rates.get_role("Encoding Lead").benchmark is None


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


def test_selection_status_wrong_shape_is_an_error(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["status"] = []
    assert any("invalid status" in e for e in validate_selection(selection))


@pytest.mark.parametrize(
    "path",
    [
        ("org_base", "item"),
        ("selections", 0, "item"),
        ("selections", 0, "note"),
        ("notes",),
    ],
    ids=("org-base-item", "line-item", "line-note", "notes"),
)
def test_selection_known_text_fields_reject_non_strings(
    portfolio_selections, path
):
    selection = _selection(portfolio_selections)
    _set_path(selection, path, ["not", "text"])
    assert validate_selection(selection)


def test_selection_text_fields_reject_lone_unicode_surrogates(
    portfolio_selections,
):
    selection = _selection(portfolio_selections)
    selection["funder"] = "\ud800"
    assert any("funder" in error for error in validate_selection(selection))


def test_selection_target_must_be_number(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["target_usd"] = "2M"
    assert any("target_usd" in e for e in validate_selection(selection))


def test_selection_target_must_be_non_negative(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["target_usd"] = -1
    assert any("non-negative" in e for e in validate_selection(selection))


def test_selection_target_zero_is_valid(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["target_usd"] = 0
    assert validate_selection(selection) == []


def test_unrepresentably_large_number_is_rejected(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["target_usd"] = 10**10000
    assert any("target_usd" in e for e in validate_selection(selection))


def test_unrepresentably_large_window_is_rejected(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["window_months"] = 10**10000
    assert any("window_months" in e for e in validate_selection(selection))


@pytest.mark.parametrize("value", NON_FINITE)
@pytest.mark.parametrize(
    "path",
    [
        ("target_usd",),
        ("org_base", "fraction"),
        ("selections", 0, "fraction"),
    ],
    ids=("target", "org-base-fraction", "selection-fraction"),
)
def test_selection_numeric_fields_must_be_finite(
    portfolio_selections, path, value
):
    selection = deepcopy(_selection(portfolio_selections))
    _set_path(selection, path, value)
    assert validate_selection(selection)


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


def test_selection_line_entry_must_be_mapping(portfolio_selections):
    selection = _selection(portfolio_selections)
    selection["selections"] = ["alpha"]
    assert any(
        "selections[0] must be a mapping" in e
        for e in validate_selection(selection)
    )


def test_selection_from_dict_skips_non_dict_lines(portfolio_selections):
    data = _selection(portfolio_selections)
    data["selections"].insert(0, "alpha")
    selection = Selection.from_dict(data)
    assert [line.item for line in selection.selections] == [
        "alpha",
        "gamma-units",
    ]


def test_selection_from_dict_preserves_explicit_zero(
    portfolio_selections,
):
    selection = Selection.from_dict(portfolio_selections[2])
    fractions = {line.item: line.fraction for line in selection.selections}
    assert fractions["beta"] == 0.0
    assert selection.selections[1].note == "declared, not billed here"
