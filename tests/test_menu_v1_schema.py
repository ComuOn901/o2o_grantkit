"""Schema coverage for the v1 parametric budget model."""

from copy import deepcopy

import pytest

from grantkit.menu import (
    Menu,
    Rates,
    Selection,
    as_number,
    validate_menu,
    validate_rates,
    validate_selection,
)


def _estimate(central=4.0):
    return {
        "central": central,
        "low": central / 2,
        "high": central * 1.5,
        "basis": "assumed",
        "source": "synthetic v1 test",
    }


def _kind():
    return {
        "title": "Program coverage",
        "doc": "Cover a program in a configurable number of places.",
        "type": "program-coverage",
        "params": {
            "scale": {
                "type": "number",
                "min": 0,
                "max": 10,
                "default": 2.0,
                "unit": "modules",
                "doc": "Work per place.",
            },
            "places": {
                "type": "integer",
                "min": 1,
                "max": 56,
                "default": 2,
            },
            "tier": {
                "type": "enum",
                "values": ["basic", "full"],
                "default": "basic",
            },
            "verified": {"type": "boolean", "default": False},
            "program": {"type": "string", "default": "SNAP"},
        },
        "derived": {
            "modules": {"product": ["scale", "places", 2]},
            "work": {"sum": ["modules", "places", 1]},
        },
        "resourcing": {
            "fte_months": {
                "Encoding Lead": {
                    "const": 1,
                    "per": {"modules": 0.25},
                },
                "Research Engineer": [
                    {
                        "per": {"places": 0.5},
                        "when": {"verified": [True]},
                    },
                    {
                        "per": {"places": 0.25},
                        "when": {"verified": [False]},
                    },
                ],
            },
            "units": {"module": {"per": {"modules": 1}}},
            "contract_usd": {"by": {"tier": {"full": 1000}}},
            "recurring_usd_per_year": {
                "per": {"places": 100},
                "when": {"tier": ["full"]},
            },
        },
        "duration_months": [{"const": 1}, {"per": {"places": 0.5}}],
        "dependencies": {"by": {"tier": {"full": ["foundation"]}}},
        "revenue": [
            {
                "stream": "determinations",
                "family": "B",
                "unit": "determination",
                "price_usd": {"const": 1, "per": {"scale": 0.5}},
                "volume_per_year": [
                    0,
                    {"per": {"modules": 100}},
                    [
                        {
                            "per": {"modules": 100},
                            "when": {"verified": [True]},
                        },
                        {
                            "per": {"modules": 50},
                            "when": {"verified": [False]},
                        },
                    ],
                ],
                "starts": "completion",
                "ramp_months": 6,
                "provenance": ["synthetic"],
            }
        ],
        "title_template": "{program} {tier}, {places} places",
        "what": "Parameterized coverage.",
        "evidence": "Coverage report published.",
        "status": "planned",
        "provenance": ["synthetic"],
    }


def _menu():
    return {
        "schema": "grantkit-menu/v1",
        "currency": "USD",
        "overheads": {
            "fiscal_sponsorship_rate": 0.07,
            "provenance": "synthetic",
        },
        "unit_costs": {
            "module": {
                "usd_per_unit": 2.5,
                "derivation": "synthetic",
                "provenance": ["synthetic"],
            }
        },
        "kinds": {"coverage": _kind()},
        "kind_presets": {
            "snap": {
                "kind": "coverage",
                "title": "SNAP",
                "params": {"program": "SNAP", "places": 5},
            }
        },
        "items": [
            {
                "id": "foundation",
                "type": "platform",
                "title": "Foundation",
                "what": "Shared foundation.",
                "evidence": "Release published.",
                "status": "in-flight",
                "duration_months": 6,
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "fte_months": {"Encoding Lead": 2},
                    "units": {"module": 10},
                    "contract_usd": 100,
                    "recurring_usd_per_year": 120,
                    "amount_usd": 50,
                },
                "revenue": [
                    {
                        "stream": "licenses",
                        "family": "A",
                        "unit": "license",
                        "price_usd": 5,
                        "volume_per_year": [10, 20],
                        "starts": "start",
                        "ramp_months": 3,
                        "provenance": ["synthetic"],
                    }
                ],
            },
            {
                "id": "snap-full",
                "kind": "coverage",
                "params": {
                    "scale": 3,
                    "places": 4,
                    "tier": "full",
                    "verified": True,
                    "program": "SNAP",
                },
                "what": "SNAP coverage.",
                "evidence": "Certification published.",
                "status": "planned",
                "dependencies": ["foundation"],
                "provenance": ["synthetic"],
            },
            {
                "id": "org-base",
                "type": "org-base",
                "title": "Organization base",
                "what": "Maintain the organization.",
                "evidence": "Audited budget published.",
                "status": "in-flight",
                "duration_months": 12,
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "roster": [
                        {"role": "Encoding Lead", "fte": 0.5, "months": 9}
                    ],
                    "non_personnel_usd_per_year": 10000,
                },
            },
        ],
    }


def _rates():
    return {
        "schema": "grantkit-rates/v1",
        "provider": "synthetic 1.0",
        "generated": "2026-08-15",
        "currency": "USD",
        "roles": [
            {
                "role": "Encoding Lead",
                "loaded_usd": 240000,
                "base_usd": 180000,
                "capacity_fte": 1.5,
                "components": [
                    {
                        "name": "benefits",
                        "amount_usd": 60000,
                        "basis": "configured",
                        "source": "synthetic",
                    }
                ],
                "benchmark": {
                    "source": "synthetic",
                    "percentile": 75,
                    "value_usd": 150000,
                },
                "provenance": ["synthetic"],
            }
        ],
    }


def _instance(instance_id="medicaid-full"):
    return {
        "id": instance_id,
        "kind": "coverage",
        "params": {
            "scale": 4,
            "places": 12,
            "tier": "full",
            "verified": False,
            "program": "Medicaid",
        },
        "title": "Medicaid full",
        "dependencies": ["foundation"],
        "provenance": ["synthetic"],
    }


def _selection():
    return {
        "schema": "grantkit-selection/v1",
        "id": "proposal",
        "funder": "Synthetic Fund",
        "status": "draft",
        "target_usd": 500000,
        "window_months": 18,
        "horizon_months": 36,
        "org_base": {"item": "org-base", "fraction": 0.1},
        "selections": [
            {"item": "snap-full", "fraction": 0.5, "start_month": 3},
            {
                "instance": _instance(),
                "fraction": 0.25,
                "start_month": 6,
                "note": "Selection-private package.",
            },
        ],
        "notes": "Synthetic v1 selection.",
    }


def _set_path(data, path, value):
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _rules(errors):
    return {getattr(error, "rule", None) for error in errors}


def _assert_rule(errors, rule):
    assert errors, "mutation unexpectedly passed validation"
    assert rule in _rules(errors), [str(error) for error in errors]


def _assert_version_error(errors, construct, required_schema):
    messages = [str(error) for error in errors]
    assert any(
        f"construct '{construct}'" in message and required_schema in message
        for message in messages
    ), messages


def test_complete_v1_documents_validate():
    menu = _menu()
    assert validate_menu(menu) == []
    assert validate_rates(_rates()) == []
    assert validate_selection(_selection(), menu) == []


def test_v1_documents_parse_new_fields():
    menu = Menu.from_dict(_menu())
    rates = Rates.from_dict(_rates())
    selection = Selection.from_dict(_selection())

    assert menu.schema == "grantkit-menu/v1"
    assert list(menu.kinds) == ["coverage"]
    assert menu.kind_presets["snap"].params["places"] == 5
    assert menu.items[-1].resourcing.roster[0].fte == 0.5
    assert rates.roles[0].capacity_fte == 1.5
    assert selection.horizon_months == 36
    assert selection.selections[0].start_month == 3
    assert selection.selections[1].instance is not None
    assert selection.selections[1].instance.id == "medicaid-full"


def test_v0_fixture_documents_remain_valid(
    portfolio_menu, portfolio_rates, portfolio_selections
):
    assert validate_menu(portfolio_menu) == []
    assert validate_rates(portfolio_rates) == []
    for selection in portfolio_selections:
        assert validate_selection(selection, portfolio_menu) == []


def test_menu_v1_constructs_require_the_v1_marker():
    menu = _menu()
    menu["schema"] = "grantkit-menu/v0"
    errors = validate_menu(menu)

    for construct in (
        "kinds",
        "kind_presets",
        "kind",
        "params",
        "revenue",
        "roster",
        "non_personnel_usd_per_year",
    ):
        _assert_version_error(errors, construct, "grantkit-menu/v1")


def test_rates_v1_constructs_require_the_v1_marker():
    rates = _rates()
    rates["schema"] = "grantkit-rates/v0"
    errors = validate_rates(rates)

    _assert_version_error(errors, "capacity_fte", "grantkit-rates/v1")


def test_selection_v1_constructs_require_the_v1_marker():
    selection = _selection()
    selection["schema"] = "grantkit-selection/v0"
    errors = validate_selection(selection, _menu())

    for construct in ("horizon_months", "start_month", "instance"):
        _assert_version_error(errors, construct, "grantkit-selection/v1")


def test_estimates_require_the_matching_v1_schema_markers(
    portfolio_menu, portfolio_rates
):
    portfolio_menu["unit_costs"]["module"]["usd_per_unit"] = _estimate()
    menu_errors = validate_menu(portfolio_menu)
    _assert_version_error(menu_errors, "estimate", "grantkit-menu/v1")

    portfolio_rates["roles"][0]["loaded_usd"] = _estimate(320000)
    rates_errors = validate_rates(portfolio_rates)
    _assert_version_error(rates_errors, "estimate", "grantkit-rates/v1")


def test_nested_kind_revenue_and_estimate_name_required_menu_marker(
    portfolio_menu,
):
    portfolio_menu["kinds"] = {
        "nested": {
            "params": {},
            "resourcing": {"amount_usd": 1},
            "revenue": [
                {
                    "stream": "nested-revenue",
                    "family": "earned",
                    "unit": "delivery",
                    "price_usd": _estimate(),
                    "volume_per_year": [1],
                }
            ],
        }
    }

    errors = validate_menu(portfolio_menu)

    for construct in ("kinds", "revenue", "estimate"):
        _assert_version_error(errors, construct, "grantkit-menu/v1")


def test_nested_instance_revenue_and_estimate_name_required_selection_marker():
    selection = {
        "schema": "grantkit-selection/v0",
        "id": "nested-instance",
        "funder": "Synthetic Fund",
        "status": "draft",
        "window_months": 12,
        "selections": [
            {
                "instance": {
                    "id": "private-work",
                    "kind": "coverage",
                    "params": {},
                    "revenue": [
                        {
                            "stream": "nested-revenue",
                            "family": "earned",
                            "unit": "delivery",
                            "price_usd": _estimate(),
                            "volume_per_year": [1],
                        }
                    ],
                },
                "fraction": 1,
            }
        ],
    }

    errors = validate_selection(selection, _menu())

    for construct in ("instance", "revenue", "estimate"):
        _assert_version_error(errors, construct, "grantkit-selection/v1")


def test_v0_identifiers_named_central_are_not_estimates(
    portfolio_menu, portfolio_rates
):
    portfolio_menu["unit_costs"]["central"] = {
        "usd_per_unit": 5,
        "derivation": "synthetic central unit",
        "provenance": ["synthetic"],
    }
    portfolio_menu["items"][1]["resourcing"]["fte_months"] = {"central": 6}
    portfolio_rates["roles"][0]["role"] = "central"

    assert validate_menu(portfolio_menu) == []
    assert validate_rates(portfolio_rates) == []


def test_kind_form_identifiers_and_enum_values_named_central_are_not_estimates(
    portfolio_menu,
):
    portfolio_menu["kinds"] = {
        "central-names": {
            "params": {
                "central": {"type": "number", "default": 1},
                "tier": {
                    "type": "enum",
                    "values": ["central"],
                    "default": "central",
                },
            },
            "resourcing": {
                "amount_usd": {
                    "per": {"central": 1},
                    "by": {"tier": {"central": 2}},
                }
            },
        }
    }

    errors = validate_menu(portfolio_menu)

    _assert_version_error(errors, "kinds", "grantkit-menu/v1")
    assert not any("construct 'estimate'" in str(error) for error in errors)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0.0),
        (3, 3.0),
        (2.5, 2.5),
        ({"central": 7}, 7.0),
        (_estimate(4), 4.0),
    ],
)
def test_as_number_accepts_numbers_and_estimates(value, expected):
    assert as_number(value) == expected


@pytest.mark.parametrize(
    "value",
    [True, "4", None, float("inf"), {"central": -1}],
)
def test_as_number_rejects_non_cost_scalars(value):
    with pytest.raises(ValueError):
        as_number(value)


ESTIMATE_MENU_PATHS = [
    ("unit_costs", "module", "usd_per_unit"),
    ("items", 0, "resourcing", "fte_months", "Encoding Lead"),
    ("items", 0, "resourcing", "contract_usd"),
    ("items", 0, "resourcing", "recurring_usd_per_year"),
    ("items", 0, "resourcing", "amount_usd"),
    ("items", 2, "resourcing", "non_personnel_usd_per_year"),
    ("items", 0, "revenue", 0, "price_usd"),
    ("items", 0, "revenue", 0, "volume_per_year", 0),
    ("kinds", "coverage", "resourcing", "fte_months", "Encoding Lead"),
    ("kinds", "coverage", "resourcing", "units", "module"),
    ("kinds", "coverage", "resourcing", "contract_usd"),
    ("kinds", "coverage", "resourcing", "recurring_usd_per_year"),
    ("kinds", "coverage", "resourcing", "amount_usd"),
    (
        "kinds",
        "coverage",
        "resourcing",
        "non_personnel_usd_per_year",
    ),
    ("kinds", "coverage", "duration_months"),
    ("kinds", "coverage", "revenue", 0, "price_usd"),
    ("kinds", "coverage", "revenue", 0, "volume_per_year", 0),
]


@pytest.mark.parametrize("path", ESTIMATE_MENU_PATHS)
def test_estimate_is_accepted_at_menu_cost_scalar_sites(path):
    menu = _menu()
    _set_path(menu, path, _estimate())
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    "path",
    [
        ("roles", 0, "loaded_usd"),
        ("roles", 0, "base_usd"),
        ("roles", 0, "components", 0, "amount_usd"),
        ("roles", 0, "benchmark", "value_usd"),
    ],
)
def test_estimate_is_accepted_at_rates_cost_scalar_sites(path):
    rates = _rates()
    _set_path(rates, path, _estimate(200000))
    assert validate_rates(rates) == []


@pytest.mark.parametrize(
    "estimate",
    [
        {},
        {"central": True},
        {"central": -1},
        {"central": float("nan")},
        {"central": float("inf")},
        {"central": 4, "low": -1},
        {"central": 4, "high": -1},
        {"central": 4, "low": 5},
        {"central": 4, "high": 3},
        {"central": 4, "basis": "guessed"},
        {"central": 4, "source": ["not text"]},
        {"central": 4, "surprise": 1},
    ],
)
def test_invalid_estimate_shapes_receive_estimate_rule(estimate):
    menu = _menu()
    menu["unit_costs"]["module"]["usd_per_unit"] = estimate
    _assert_rule(validate_menu(menu), "estimate_invalid")


@pytest.mark.parametrize(
    "form",
    [
        4,
        _estimate(),
        {"const": 2},
        {"const": _estimate()},
        {"per": {"places": 2}},
        {"per": {"places": _estimate()}},
        {"per": {"modules": 2}},
        {"by": {"tier": {"basic": 1, "full": 2}}},
        {"by": {"verified": {False: 1, True: 2}}},
        {"const": 1, "when": {"tier": ["full"]}},
        {"const": 1, "when": {"verified": [True]}},
        [{"const": 1}, {"per": {"places": 2}}],
        {
            "const": 1,
            "per": {"places": 2},
            "by": {"tier": {"full": 3}},
            "when": {"verified": [False, True]},
        },
        {"by": {"tier": {"full": _estimate()}}},
    ],
)
def test_valid_form_grammar_is_accepted(form):
    menu = _menu()
    menu["kinds"]["coverage"]["resourcing"]["contract_usd"] = form
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    "form",
    [
        -1,
        [],
        [[{"const": 1}]],
        "places * 2",
        {},
        {"when": {"tier": ["full"]}},
        {"const": 1, "multiply": {"places": 2}},
        {"const": -1},
        {"per": ["places"]},
        {"per": {"unknown": 1}},
        {"per": {"program": 1}},
        {"per": {"places": -1}},
        {"by": []},
        {"by": {}},
        {"by": {"unknown": {"x": 1}}},
        {"by": {"tier": []}},
        {"by": {"tier": {"enterprise": 1}}},
        {"by": {"tier": {"full": -1}}},
        {"const": 1, "when": []},
        {"const": 1, "when": {}},
        {"const": 1, "when": {"tier": []}},
        {"const": 1, "when": {"tier": ["enterprise"]}},
        {"const": 1, "when": {"places": [2]}},
        {"const": 1, "when": {"verified": [1]}},
    ],
)
def test_invalid_form_grammar_receives_kind_form_rule(form):
    menu = _menu()
    menu["kinds"]["coverage"]["resourcing"]["contract_usd"] = form
    _assert_rule(validate_menu(menu), "kind_form_invalid")


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("scale", 0),
        ("scale", 10),
        ("places", 1),
        ("places", 56),
        ("tier", "basic"),
        ("verified", True),
        ("verified", False),
        ("program", "Medicaid"),
    ],
)
def test_kind_param_types_and_inclusive_bounds_are_accepted(param, value):
    menu = _menu()
    menu["items"][1]["params"][param] = value
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    ("param", "negative"),
    [("scale", -0.01), ("places", -1)],
)
def test_numeric_params_without_min_use_an_implicit_zero_bound(
    param, negative
):
    menu = _menu()
    del menu["kinds"]["coverage"]["params"][param]["min"]
    menu["items"][1]["params"][param] = negative

    _assert_rule(validate_menu(menu), "kind_param_invalid")


def test_null_numeric_min_uses_the_implicit_zero_bound():
    menu = _menu()
    menu["kinds"]["coverage"]["params"]["scale"]["min"] = None
    menu["items"][1]["params"]["scale"] = -0.01

    _assert_rule(validate_menu(menu), "kind_param_invalid")


def test_negative_cost_probe_without_declared_min_fails_validation():
    menu = _menu()
    menu["kinds"] = {
        "cost": {
            "params": {"quantity": {"type": "number", "default": 1}},
            "resourcing": {"amount_usd": {"per": {"quantity": 100000}}},
        }
    }
    menu["kind_presets"] = {}
    menu["items"] = [
        {
            "id": "negative-cost",
            "kind": "cost",
            "params": {"quantity": -1},
            "what": "Exercise the implicit numeric bound.",
            "evidence": "Validation rejects the selection.",
            "status": "planned",
            "dependencies": [],
            "provenance": ["synthetic"],
        }
    ]

    errors = validate_menu(menu)

    _assert_rule(errors, "kind_param_invalid")
    assert any("quantity" in str(error) for error in errors)


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("scale", -0.01),
        ("scale", 10.01),
        ("scale", True),
        ("places", 0),
        ("places", 57),
        ("places", 2.5),
        ("places", True),
        ("tier", "enterprise"),
        ("verified", 1),
        ("verified", "true"),
        ("program", 10),
        ("undeclared", 1),
    ],
)
def test_invalid_kind_item_param_values_receive_param_rule(param, value):
    menu = _menu()
    menu["items"][1]["params"][param] = value
    _assert_rule(validate_menu(menu), "kind_param_invalid")


@pytest.mark.parametrize(
    ("name", "definition"),
    [
        ("bad", {"type": "decimal", "default": 1}),
        ("bad", {"type": "number"}),
        ("bad", {"type": "number", "min": 2, "max": 1, "default": 1}),
        ("bad", {"type": "integer", "default": 1.5}),
        ("bad", {"type": "enum", "values": [], "default": "x"}),
        (
            "bad",
            {"type": "enum", "values": ["x", "x"], "default": "x"},
        ),
        ("bad", {"type": "boolean", "min": 0, "default": False}),
        ("bad", {"type": "string", "max": 4, "default": "x"}),
    ],
)
def test_invalid_kind_param_definitions_receive_param_rule(name, definition):
    menu = _menu()
    menu["kinds"]["coverage"]["params"][name] = definition
    _assert_rule(validate_menu(menu), "kind_param_invalid")


def test_kind_item_may_omit_params_with_defaults():
    menu = _menu()
    menu["items"][1]["params"] = {}
    assert validate_menu(menu) == []


def test_params_without_kind_are_rejected():
    menu = _menu()
    menu["items"][0]["params"] = {"scale": 1}
    _assert_rule(validate_menu(menu), "kind_param_invalid")


def test_unknown_kind_is_rejected():
    menu = _menu()
    menu["items"][1]["kind"] = "unknown"
    _assert_rule(validate_menu(menu), "kind_unknown")


def test_derived_values_may_reference_earlier_derived_values_and_constants():
    menu = _menu()
    menu["kinds"]["coverage"]["derived"] = {
        "modules": {"sum": ["places", 2]},
        "work": {"product": ["modules", "scale", 0.5]},
    }
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    "derived",
    [
        [],
        {"places": {"sum": [1, 2]}},
        {"bad": "places + 1"},
        {"bad": {}},
        {"bad": {"sum": [], "product": [1]}},
        {"bad": {"sum": []}},
        {"bad": {"sum": ["unknown"]}},
        {"bad": {"sum": ["program"]}},
        {
            "later": {"sum": ["earlier", 1]},
            "earlier": {"sum": ["places", 1]},
        },
        {
            "left": {"sum": ["right", 1]},
            "right": {"sum": ["left", 1]},
        },
    ],
)
def test_invalid_derived_expressions_receive_derived_rule(derived):
    menu = _menu()
    menu["kinds"]["coverage"]["derived"] = derived
    _assert_rule(validate_menu(menu), "derived_invalid")


def test_partial_preset_is_valid():
    menu = _menu()
    menu["kind_presets"]["snap"]["params"] = {"program": "SNAP"}
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    ("mutation", "rule"),
    [
        ("unknown-kind", "kind_unknown"),
        ("unknown-param", "kind_param_invalid"),
        ("out-of-bounds", "kind_param_invalid"),
        ("wrong-type", "kind_param_invalid"),
        ("missing-title", "kind_param_invalid"),
    ],
)
def test_invalid_kind_presets_are_rejected(mutation, rule):
    menu = _menu()
    preset = menu["kind_presets"]["snap"]
    if mutation == "unknown-kind":
        preset["kind"] = "missing"
    elif mutation == "unknown-param":
        preset["params"]["unknown"] = 1
    elif mutation == "out-of-bounds":
        preset["params"]["places"] = 57
    elif mutation == "wrong-type":
        preset["params"]["places"] = 1.5
    else:
        del preset["title"]
    _assert_rule(validate_menu(menu), rule)


@pytest.mark.parametrize(
    "override",
    [
        {"fte_months": {"Encoding Lead": 1}},
        {"units": {"module": 12}},
        {"contract_usd": 200},
        {"recurring_usd_per_year": 300},
        {"amount_usd": 400},
        {
            "roster": [{"role": "Encoding Lead", "fte": 0.25}],
            "non_personnel_usd_per_year": 500,
        },
    ],
)
def test_kind_items_accept_concrete_resourcing_overrides(override):
    menu = _menu()
    menu["items"][1]["resourcing"] = override
    assert validate_menu(menu) == []


def test_kind_item_accepts_explicit_metadata_and_revenue_overrides():
    menu = _menu()
    item = menu["items"][1]
    item.update(
        {
            "title": "Explicit title",
            "type": "explicit-type",
            "duration_months": 4,
            "revenue": deepcopy(menu["items"][0]["revenue"]),
        }
    )
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stream", ""),
        ("family", None),
        ("unit", 1),
        ("price_usd", -1),
        ("price_usd", "five"),
        ("volume_per_year", []),
        ("volume_per_year", [-1]),
        ("starts", "award"),
        ("ramp_months", -1),
        ("ramp_months", True),
        ("provenance", "synthetic"),
    ],
)
def test_invalid_explicit_revenue_streams_receive_revenue_rule(field, value):
    menu = _menu()
    menu["items"][0]["revenue"][0][field] = value
    _assert_rule(validate_menu(menu), "revenue_invalid")


@pytest.mark.parametrize(
    ("field", "value", "expected_rule"),
    [
        ("price_usd", {"per": {"unknown": 1}}, "kind_form_invalid"),
        ("price_usd", -1, "kind_form_invalid"),
        ("volume_per_year", [], "revenue_invalid"),
        ("volume_per_year", [[-1]], "kind_form_invalid"),
        ("starts", "award", "revenue_invalid"),
        ("ramp_months", -1, "revenue_invalid"),
    ],
)
def test_invalid_parametric_revenue_is_rejected(field, value, expected_rule):
    menu = _menu()
    menu["kinds"]["coverage"]["revenue"][0][field] = value
    _assert_rule(validate_menu(menu), expected_rule)


@pytest.mark.parametrize("start_month", [0, 1, 120])
def test_selection_start_month_accepts_non_negative_integers(start_month):
    selection = _selection()
    selection["selections"][0]["start_month"] = start_month
    assert validate_selection(selection, _menu()) == []


@pytest.mark.parametrize("start_month", [-1, 1.5, True, "3"])
def test_selection_start_month_rejects_invalid_values(start_month):
    selection = _selection()
    selection["selections"][0]["start_month"] = start_month
    errors = validate_selection(selection, _menu())
    assert any("start_month" in str(error) for error in errors)


@pytest.mark.parametrize("horizon", [1, 12, 37])
def test_selection_horizon_accepts_positive_integers(horizon):
    selection = _selection()
    selection["horizon_months"] = horizon
    assert validate_selection(selection, _menu()) == []


@pytest.mark.parametrize("horizon", [0, -1, 1.5, True, "12"])
def test_selection_horizon_rejects_invalid_values(horizon):
    selection = _selection()
    selection["horizon_months"] = horizon
    errors = validate_selection(selection, _menu())
    assert any("horizon_months" in str(error) for error in errors)


def test_selection_horizon_defaults_to_window_when_parsed():
    selection = _selection()
    del selection["horizon_months"]
    assert validate_selection(selection, _menu()) == []
    assert Selection.from_dict(selection).horizon_months == 18


@pytest.mark.parametrize(
    "roster",
    [
        [{"role": "Encoding Lead", "fte": 0}],
        [{"role": "Encoding Lead", "fte": 1, "months": 0}],
        [{"role": "Encoding Lead", "fte": 1.25, "months": 18.5}],
    ],
)
def test_roster_accepts_non_negative_plain_decisions(roster):
    menu = _menu()
    menu["items"][2]["resourcing"]["roster"] = roster
    assert validate_menu(menu) == []


@pytest.mark.parametrize(
    "roster",
    [
        "Encoding Lead",
        ["Encoding Lead"],
        [{"role": "", "fte": 1}],
        [{"role": "Encoding Lead", "fte": -1}],
        [{"role": "Encoding Lead", "fte": _estimate()}],
        [{"role": "Encoding Lead", "fte": 1, "months": -1}],
        [{"role": "Encoding Lead", "fte": 1, "months": _estimate()}],
    ],
)
def test_roster_rejects_invalid_shapes_and_estimate_decisions(roster):
    menu = _menu()
    menu["items"][2]["resourcing"]["roster"] = roster
    errors = validate_menu(menu)
    assert errors
    assert any("roster" in str(error) for error in errors)


@pytest.mark.parametrize("capacity", [0, 0.5, 3])
def test_capacity_fte_accepts_non_negative_numbers(capacity):
    rates = _rates()
    rates["roles"][0]["capacity_fte"] = capacity
    assert validate_rates(rates) == []
    assert Rates.from_dict(rates).roles[0].capacity_fte == float(capacity)


@pytest.mark.parametrize("capacity", [-1, True, "one", _estimate()])
def test_capacity_fte_rejects_invalid_or_estimate_values(capacity):
    rates = _rates()
    rates["roles"][0]["capacity_fte"] = capacity
    errors = validate_rates(rates)
    assert any("capacity_fte" in str(error) for error in errors)


def test_inline_instance_validates_against_kind_params():
    assert validate_selection(_selection(), _menu()) == []


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("places", 0),
        ("places", 2.5),
        ("tier", "enterprise"),
        ("verified", 1),
        ("program", 3),
        ("undeclared", "value"),
    ],
)
def test_inline_instance_invalid_params_receive_param_rule(param, value):
    selection = _selection()
    selection["selections"][1]["instance"]["params"][param] = value
    _assert_rule(validate_selection(selection, _menu()), "kind_param_invalid")


def test_inline_instance_unknown_kind_is_rejected_with_menu_context():
    selection = _selection()
    selection["selections"][1]["instance"]["kind"] = "missing"
    _assert_rule(validate_selection(selection, _menu()), "kind_unknown")


@pytest.mark.parametrize(
    "line",
    [{"fraction": 1}, {"item": "x", "fraction": 1, "instance": _instance()}],
)
def test_selection_line_enforces_item_xor_instance(line):
    selection = _selection()
    selection["selections"] = [line]
    _assert_rule(validate_selection(selection, _menu()), "selection_invalid")


def test_inline_instance_id_must_not_collide_with_menu_item():
    selection = _selection()
    selection["selections"][1]["instance"]["id"] = "foundation"
    _assert_rule(
        validate_selection(selection, _menu()), "instance_id_collision"
    )


def test_inline_instance_ids_must_be_unique_within_selection():
    selection = _selection()
    selection["selections"].append(
        {"instance": _instance(), "fraction": 1, "start_month": 0}
    )
    _assert_rule(
        validate_selection(selection, _menu()), "instance_id_collision"
    )


@pytest.mark.parametrize("instance_id", ["", "Bad ID", "under_score"])
def test_inline_instance_id_must_match_item_id_grammar(instance_id):
    selection = _selection()
    selection["selections"][1]["instance"]["id"] = instance_id
    _assert_rule(
        validate_selection(selection, _menu()), "instance_id_collision"
    )


@pytest.mark.parametrize(
    "field",
    ["resourcing", "duration_months", "dependencies", "revenue"],
)
def test_inline_instance_accepts_concrete_overrides(field):
    selection = _selection()
    instance = selection["selections"][1]["instance"]
    values = {
        "resourcing": {"contract_usd": _estimate()},
        "duration_months": 4,
        "dependencies": ["foundation", "other"],
        "revenue": deepcopy(_menu()["items"][0]["revenue"]),
    }
    instance[field] = values[field]
    assert validate_selection(selection, _menu()) == []


def test_inline_instance_revenue_estimates_are_accepted():
    selection = _selection()
    instance = selection["selections"][1]["instance"]
    instance["revenue"] = deepcopy(_menu()["items"][0]["revenue"])
    instance["revenue"][0]["price_usd"] = _estimate()
    instance["revenue"][0]["volume_per_year"] = [_estimate()]
    assert validate_selection(selection, _menu()) == []
