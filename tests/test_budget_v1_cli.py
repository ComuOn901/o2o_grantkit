"""v0.4 CLI, gate, renderer, and model-bundle integration contracts."""

from __future__ import annotations

import copy
import json

import pytest
from click.testing import CliRunner

from grantkit.cli import main
from grantkit.menu import load_portfolio, run_gates
from grantkit.menu.model import model_bundle


def _invoke(*args):
    return CliRunner().invoke(main, ["budget", *map(str, args)])


def _estimate(central, low=None, high=None, *, basis="configured"):
    value = {
        "central": central,
        "basis": basis,
        "source": "synthetic v1 integration fixture",
    }
    if low is not None:
        value["low"] = low
    if high is not None:
        value["high"] = high
    return value


def _v1_menu():
    return {
        "schema": "grantkit-menu/v1",
        "currency": "USD",
        "overheads": {
            "fiscal_sponsorship_rate": 0.1,
            "provenance": "synthetic",
        },
        "unit_costs": {
            "token": {
                "usd_per_unit": _estimate(3, 2, 4),
                "derivation": "synthetic unit price",
                "provenance": ["synthetic"],
            }
        },
        "kinds": {
            "widget": {
                "title": "Widget",
                "doc": "Parametric widget work.",
                "type": "delivery",
                "what": "Deliver the configured widget.",
                "evidence": "Widget accepted.",
                "params": {
                    "count": {
                        "type": "integer",
                        "min": 1,
                        "max": 10,
                        "default": 2,
                    },
                    "label": {"type": "string", "default": "Core"},
                    "enabled": {"type": "boolean", "default": True},
                },
                "derived": {
                    "twice": {"product": ["count", 2]},
                    "plus_one": {"sum": ["twice", 1]},
                },
                "resourcing": {
                    "fte_months": {
                        "Analyst": {"per": {"count": 1}},
                    },
                    "units": {"token": {"per": {"twice": 1}}},
                    "amount_usd": [
                        {"const": _estimate(10, 8, 14)},
                        {"per": {"count": _estimate(2, 1, 3)}},
                    ],
                },
                "duration_months": {"const": 6},
                "dependencies": [],
                "revenue": [
                    {
                        "stream": "subscriptions",
                        "family": "earned",
                        "unit": "subscription",
                        "price_usd": _estimate(2, 1, 3, basis="assumed"),
                        "volume_per_year": [
                            {"per": {"count": 120}},
                            {"const": 480},
                        ],
                        "starts": "start",
                        "ramp_months": 6,
                        "provenance": ["synthetic"],
                    }
                ],
                "title_template": "{label} widget x{count}",
                "provenance": ["synthetic"],
            }
        },
        "kind_presets": {
            "starter": {
                "kind": "widget",
                "title": "Starter widget",
                "params": {"count": 1, "label": "Starter"},
            }
        },
        "items": [
            {
                "id": "plain-b",
                "type": "operations",
                "title": "Plain B",
                "what": "Second plain work block.",
                "evidence": "Plain B completed.",
                "status": "planned",
                "duration_months": 12,
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "fte_months": {"Analyst": 6},
                    "amount_usd": 120,
                },
            },
            {
                "id": "kind-z",
                "kind": "widget",
                "params": {"count": 3, "label": "Configured"},
                "what": "Configured widget work.",
                "evidence": "Configured widget accepted.",
                "status": "planned",
                "dependencies": [],
                "provenance": ["synthetic item"],
            },
            {
                "id": "org-base",
                "type": "org-base",
                "title": "Organization base",
                "what": "Maintain organization capacity.",
                "evidence": "Organization remains operational.",
                "status": "planned",
                "duration_months": 12,
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "roster": [{"role": "Analyst", "fte": 0.25, "months": 12}],
                    "non_personnel_usd_per_year": 1200,
                },
            },
            {
                "id": "plain-a",
                "type": "operations",
                "title": "Plain A",
                "what": "First plain work block.",
                "evidence": "Plain A completed.",
                "status": "planned",
                "duration_months": 12,
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "fte_months": {"Analyst": 6},
                    "amount_usd": 100,
                },
            },
        ],
    }


def _v1_rates(capacity=10.0):
    return {
        "schema": "grantkit-rates/v1",
        "provider": "synthetic v1 provider",
        "generated": "2026-08-15",
        "scenario": "v1-tests",
        "currency": "USD",
        "roles": [
            {
                "role": "Analyst",
                "loaded_usd": _estimate(120000, 100000, 140000),
                "capacity_fte": capacity,
                "provenance": ["synthetic"],
            }
        ],
    }


def _selection(
    selection_id,
    item,
    *,
    fraction=1.0,
    status="draft",
    window=12,
    horizon=24,
    start=0,
    org_base=False,
):
    value = {
        "schema": "grantkit-selection/v1",
        "id": selection_id,
        "funder": f"Funder {selection_id}",
        "status": status,
        "window_months": window,
        "horizon_months": horizon,
        "selections": [
            {"item": item, "fraction": fraction, "start_month": start}
        ],
    }
    if org_base:
        value["org_base"] = {"item": "org-base", "fraction": 0.1}
    return value


def _v1_selections():
    return [
        _selection("sel-zeta", "plain-b", fraction=0.5),
        _selection(
            "sel-alpha",
            "kind-z",
            fraction=0.4,
            status="live",
            org_base=True,
        ),
    ]


def _v1_root(make_portfolio, *, menu=None, rates=None, selections=None):
    return make_portfolio(
        menu=_v1_menu() if menu is None else menu,
        rates=_v1_rates() if rates is None else rates,
        selections=_v1_selections() if selections is None else selections,
    )


def _rules(root, selection_id=None):
    return [
        item
        for item in run_gates(load_portfolio(root), selection_id)
        if item.level == "warning"
    ]


# -- budget --all --json -----------------------------------------------


def test_all_json_has_one_compilation_per_selection(make_portfolio):
    result = _invoke("--all", "--json", _v1_root(make_portfolio))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert list(payload) == ["selections"]
    assert list(payload["selections"]) == ["sel-alpha", "sel-zeta"]
    for selection_id, compilation in payload["selections"].items():
        assert compilation["selection_id"] == selection_id
        assert compilation["periods"]
        assert "revenue" in compilation
        assert "estimates" in compilation


def test_compiled_json_carries_weighted_org_base_other_costs(make_portfolio):
    menu = _v1_menu()
    resourcing = menu["items"][2]["resourcing"]
    del resourcing["non_personnel_usd_per_year"]
    resourcing["non_personnel"] = [
        {
            "label": "Cloud",
            "usd_per_year": 1200,
            "basis": "configured",
            "source": "synthetic cloud source",
        },
        {
            "label": "Practitioner review",
            "usd_total": 900,
            "basis": "assumed",
        },
    ]
    result = _invoke(
        "--selection",
        "sel-alpha",
        "--json",
        _v1_root(make_portfolio, menu=menu),
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["org_base"]["non_personnel"] == [
        {
            "label": "Cloud",
            "usd": 120.0,
            "basis": "configured",
            "source": "synthetic cloud source",
        },
        {
            "label": "Practitioner review",
            "usd": 90.0,
            "basis": "assumed",
            "source": None,
        },
    ]


def test_all_json_selection_keys_are_sorted_in_bytes(make_portfolio):
    result = _invoke("--all", "--json", _v1_root(make_portfolio))
    assert result.exit_code == 0
    assert result.stdout.index('"sel-alpha"') < result.stdout.index(
        '"sel-zeta"'
    )


def test_all_json_is_byte_stable_across_runs(make_portfolio):
    root = _v1_root(make_portfolio)
    first = _invoke("--all", "--json", root)
    second = _invoke("--all", "--json", root)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout_bytes == second.stdout_bytes
    assert first.stderr_bytes == second.stderr_bytes


def test_all_json_stdout_is_pure_when_warnings_exist(make_portfolio):
    rates = _v1_rates(capacity=0.1)
    result = _invoke("--all", "--json", _v1_root(make_portfolio, rates=rates))
    assert result.exit_code == 0
    assert set(json.loads(result.stdout)) == {"selections"}
    assert "role_over_allocated" in result.stderr
    assert "warning" not in result.stdout


def test_all_json_returns_findings_atomically_on_gate_error(make_portfolio):
    menu = _v1_menu()
    del menu["unit_costs"]["token"]
    result = _invoke("--all", "--json", _v1_root(make_portfolio, menu=menu))
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["errors"] >= 1
    assert "selections" not in payload
    assert any(item["rule"] == "unknown_unit" for item in payload["items"])
    assert "Cannot compile" in result.stderr


@pytest.mark.parametrize(
    ("args", "messages"),
    [
        (("--all",), ("--all requires --json",)),
        (
            ("--all", "--json", "--selection", "sel-alpha"),
            ("--selection cannot be used with --all",),
        ),
        (
            ("--all", "--json", "--check"),
            ("--check cannot be used with --all",),
        ),
        (
            ("--all", "--json", "--output", "budget.md"),
            ("--output cannot be used with --all",),
        ),
        (
            ("--all", "--json", "--narrative"),
            (
                "--narrative cannot be used with --all",
                "--narrative with --json requires --output",
            ),
        ),
    ],
)
def test_all_rejects_incompatible_modes(make_portfolio, args, messages):
    result = _invoke(*args, _v1_root(make_portfolio))
    assert result.exit_code == 2
    assert any(message in result.output for message in messages)


# -- normalized model export -------------------------------------------


@pytest.mark.parametrize(
    ("option", "extra"),
    [
        ("--selection", ("sel-alpha",)),
        ("--all", ("--json",)),
        ("--check", ()),
        ("--json", ()),
        ("--output", ("budget.md",)),
        ("--narrative", ()),
        ("--periods", ()),
    ],
)
def test_export_model_rejects_every_other_output_mode(
    make_portfolio, tmp_path, option, extra
):
    output = tmp_path / "model.json"
    result = _invoke(
        "--export-model",
        output,
        option,
        *extra,
        _v1_root(make_portfolio),
    )
    assert result.exit_code == 2
    assert f"{option} cannot be used with --export-model" in result.output
    assert not output.exists()


def test_export_model_has_normalized_top_level_contract(
    make_portfolio, tmp_path
):
    output = tmp_path / "model.json"
    result = _invoke("--export-model", output, _v1_root(make_portfolio))
    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "grantkit-model/v1"
    assert payload["generated_from"] == {
        "generated": "2026-08-15",
        "menu": "grantkit-menu/v1",
        "provider": "synthetic v1 provider",
        "rates": "grantkit-rates/v1",
    }
    assert payload["currency"] == "USD"
    assert payload["overheads"]["fiscal_sponsorship_rate"] == 0.1


def test_export_model_splits_unit_estimate_from_central(
    make_portfolio, tmp_path
):
    output = tmp_path / "model.json"
    result = _invoke("--export-model", output, _v1_root(make_portfolio))
    assert result.exit_code == 0
    unit = json.loads(output.read_text(encoding="utf-8"))["unit_costs"][
        "token"
    ]
    assert unit["usd_per_unit"] == 3.0
    assert unit["estimate"] == _estimate(3, 2, 4)


def test_export_model_preserves_kinds_presets_and_derived_order(
    make_portfolio, tmp_path
):
    output = tmp_path / "model.json"
    _invoke("--export-model", output, _v1_root(make_portfolio))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["kinds"]["widget"]["derived_order"] == [
        "twice",
        "plus_one",
    ]
    assert payload["kinds"]["widget"]["derived"]["twice"] == {
        "product": ["count", 2]
    }
    assert payload["kind_presets"]["starter"]["params"]["count"] == 1


def test_export_model_items_contain_raw_and_resolved_forms(
    make_portfolio, tmp_path
):
    output = tmp_path / "model.json"
    _invoke("--export-model", output, _v1_root(make_portfolio))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [entry["raw"]["id"] for entry in payload["items"]] == [
        "kind-z",
        "org-base",
        "plain-a",
        "plain-b",
    ]
    item = payload["items"][0]
    assert item["raw"]["kind"] == "widget"
    assert item["resolved"]["title"] == "Configured widget x3"
    assert item["resolved"]["derived"] == {
        "plus_one": 7.0,
        "twice": 6.0,
    }
    assert item["resolved"]["resourcing"]["units"] == {"token": 6.0}
    assert item["resolved"]["revenue"][0]["price_usd"] == 2.0


def test_export_model_preserves_itemized_non_personnel_inputs(
    make_portfolio, tmp_path
):
    menu = _v1_menu()
    resourcing = menu["items"][2]["resourcing"]
    del resourcing["non_personnel_usd_per_year"]
    resourcing["non_personnel"] = [
        {
            "label": "Cloud",
            "usd_per_year": 1200,
            "basis": "assumed",
            "source": "synthetic source",
        },
        {"label": "Corpus", "usd_total": 500},
    ]
    output = tmp_path / "model.json"
    result = _invoke(
        "--export-model",
        output,
        _v1_root(make_portfolio, menu=menu),
    )
    assert result.exit_code == 0, result.output
    item = json.loads(output.read_text(encoding="utf-8"))["items"][1]
    assert item["raw"]["resourcing"]["non_personnel"] == [
        {
            "label": "Cloud",
            "usd_per_year": 1200,
            "basis": "assumed",
            "source": "synthetic source",
        },
        {"label": "Corpus", "usd_total": 500},
    ]
    assert item["resolved"]["resourcing"]["non_personnel"] == [
        {
            "label": "Cloud",
            "usd_per_year": 1200.0,
            "basis": "assumed",
            "source": "synthetic source",
        },
        {"label": "Corpus", "usd_total": 500.0},
    ]


def test_export_model_sorts_role_and_selection_records(
    make_portfolio, tmp_path
):
    rates = _v1_rates()
    rates["roles"].insert(
        0,
        {
            "role": "Zoologist",
            "loaded_usd": 100000,
            "capacity_fte": 1,
        },
    )
    rates["roles"].append(
        {"role": "Accountant", "loaded_usd": 90000, "capacity_fte": 1}
    )
    output = tmp_path / "model.json"
    _invoke(
        "--export-model",
        output,
        _v1_root(make_portfolio, rates=rates),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [role["role"] for role in payload["rates"]["roles"]] == [
        "Accountant",
        "Analyst",
        "Zoologist",
    ]
    assert [entry["id"] for entry in payload["selections"]] == [
        "sel-alpha",
        "sel-zeta",
    ]


def test_export_model_serialization_is_sorted_and_canonical(
    make_portfolio, tmp_path
):
    output = tmp_path / "model.json"
    _invoke("--export-model", output, _v1_root(make_portfolio))
    text = output.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert (
        text
        == json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    )


def test_export_model_is_byte_identical_across_destinations(
    make_portfolio, tmp_path
):
    root = _v1_root(make_portfolio)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    result_a = _invoke("--export-model", first, root)
    result_b = _invoke("--export-model", second, root)
    assert result_a.exit_code == result_b.exit_code == 0
    assert first.read_bytes() == second.read_bytes()


def test_model_bundle_does_not_mutate_loaded_portfolio(make_portfolio):
    portfolio = load_portfolio(_v1_root(make_portfolio))
    raw_before = copy.deepcopy(
        (portfolio.menu_data, portfolio.rates_data, portfolio.selections_data)
    )
    parsed_before = copy.deepcopy(
        (portfolio.menu.raw, portfolio.rates.raw, portfolio.selections)
    )
    bundle = model_bundle(portfolio)
    assert (
        portfolio.menu_data,
        portfolio.rates_data,
        portfolio.selections_data,
    ) == raw_before
    assert (
        portfolio.menu.raw,
        portfolio.rates.raw,
        portfolio.selections,
    ) == parsed_before
    bundle["kinds"]["widget"]["params"]["count"]["default"] = 9
    assert (
        portfolio.menu_data["kinds"]["widget"]["params"]["count"]["default"]
        == 2
    )


def test_export_model_refuses_gate_errors_without_writing(
    make_portfolio, tmp_path
):
    menu = _v1_menu()
    menu["items"][1]["params"]["count"] = 99
    output = tmp_path / "model.json"
    result = _invoke(
        "--export-model",
        output,
        _v1_root(make_portfolio, menu=menu),
    )
    assert result.exit_code == 1
    assert "kind_param_invalid" in result.output
    assert "Cannot export" in result.stderr
    assert not output.exists()


def test_export_model_reports_destination_and_keeps_file_json_pure(
    make_portfolio, tmp_path
):
    output = tmp_path / "model.json"
    result = _invoke("--export-model", output, _v1_root(make_portfolio))
    assert result.exit_code == 0
    assert "Wrote model bundle to" in result.output
    assert output.name in result.output
    assert output.read_text(encoding="utf-8").startswith("{\n")


# -- phased and revenue renderers --------------------------------------


@pytest.mark.parametrize("show_periods", [False, True])
def test_rich_period_sections_are_flag_controlled(
    make_portfolio, show_periods
):
    args = ["--selection", "sel-alpha"]
    if show_periods:
        args.append("--periods")
    result = _invoke(*args, _v1_root(make_portfolio))
    assert result.exit_code == 0
    assert ("Phasing" in result.stdout) is show_periods
    assert ("Staffing" in result.stdout) is show_periods


@pytest.mark.parametrize("show_periods", [False, True])
def test_markdown_period_sections_are_flag_controlled(
    make_portfolio, tmp_path, show_periods
):
    output = tmp_path / "budget.md"
    args = ["--selection", "sel-alpha", "--output", output]
    if show_periods:
        args.append("--periods")
    result = _invoke(*args, _v1_root(make_portfolio))
    assert result.exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert ("## Phasing" in text) is show_periods
    assert ("## Staffing" in text) is show_periods


@pytest.mark.parametrize("show_periods", [False, True])
def test_json_always_contains_periods_and_staffing(
    make_portfolio, show_periods
):
    args = ["--selection", "sel-alpha", "--json"]
    if show_periods:
        args.append("--periods")
    result = _invoke(*args, _v1_root(make_portfolio))
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [period["label"] for period in payload["periods"]] == ["Y1", "Y2"]
    assert payload["periods"][0]["fte_by_role"]["Analyst"] > 0
    assert payload["periods"][0]["base_fte_by_role"] == {"Analyst": 0.25}


def test_markdown_periods_explain_empty_staffing(make_portfolio, tmp_path):
    menu = _v1_menu()
    menu["items"][3]["resourcing"] = {"amount_usd": 100}
    selection = _selection("sel-flat", "plain-a", horizon=12)
    output = tmp_path / "budget.md"
    result = _invoke(
        "--selection",
        "sel-flat",
        "--periods",
        "--output",
        output,
        _v1_root(make_portfolio, menu=menu, selections=[selection]),
    )
    assert result.exit_code == 0
    text = output.read_text(encoding="utf-8")
    assert "## Staffing" in text
    assert "No personnel are scheduled in these periods." in text


@pytest.mark.parametrize(
    "expected",
    [
        "## Revenue",
        "org-level projections, not a profit-and-loss statement",
        "Enabled revenue:",
        "Attributed revenue:",
        "Net of attributed revenue — attribution is a convention, see docs",
    ],
)
def test_markdown_revenue_contract(make_portfolio, tmp_path, expected):
    output = tmp_path / "budget.md"
    result = _invoke(
        "--selection",
        "sel-alpha",
        "--output",
        output,
        _v1_root(make_portfolio),
    )
    assert result.exit_code == 0
    assert expected in output.read_text(encoding="utf-8")


def test_rich_revenue_shows_enabled_attributed_and_net(make_portfolio):
    result = _invoke("--selection", "sel-alpha", _v1_root(make_portfolio))
    assert result.exit_code == 0
    assert "Revenue" in result.stdout
    assert "Enabled" in result.stdout
    assert "Attributed" in result.stdout
    assert "Net of attributed revenue" in result.stdout


def test_narrative_identifies_revenue_enabled_by_item(make_portfolio):
    result = _invoke(
        "--selection",
        "sel-alpha",
        "--narrative",
        _v1_root(make_portfolio),
    )
    assert result.exit_code == 0
    assert "### Configured widget x3" in result.stdout
    assert "Revenue enabled: USD " in result.stdout


# -- role capacity ------------------------------------------------------


def _capacity_inputs(total_demand, statuses=("live", "awarded")):
    menu = _v1_menu()
    each_fte_months = total_demand * 6
    menu["items"][0]["resourcing"]["fte_months"]["Analyst"] = each_fte_months
    menu["items"][3]["resourcing"]["fte_months"]["Analyst"] = each_fte_months
    selections = [
        _selection("sel-b", "plain-b", status=statuses[1], horizon=12),
        _selection("sel-a", "plain-a", status=statuses[0], horizon=12),
    ]
    return menu, selections


@pytest.mark.parametrize(
    ("demand", "warns"),
    [
        (0.9999999, False),
        (1.0, False),
        (1.0000001, False),
        (1.0000001001, True),
    ],
)
def test_role_capacity_uses_specified_relative_tolerance(
    make_portfolio, demand, warns
):
    menu, selections = _capacity_inputs(demand)
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1),
        selections=selections,
    )
    hits = [
        item for item in _rules(root) if item.rule == "role_over_allocated"
    ]
    assert bool(hits) is warns


@pytest.mark.parametrize(
    ("statuses", "warns"),
    [
        (("live", "awarded"), True),
        (("awarded", "live"), True),
        (("draft", "live"), False),
        (("withdrawn", "declined"), False),
    ],
)
def test_role_capacity_unscoped_gate_uses_only_binding_statuses(
    make_portfolio, statuses, warns
):
    menu, selections = _capacity_inputs(1.2, statuses)
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1),
        selections=selections,
    )
    hits = [
        item for item in _rules(root) if item.rule == "role_over_allocated"
    ]
    assert bool(hits) is warns


def test_role_capacity_scoped_gate_adds_nonbinding_subject(make_portfolio):
    menu, selections = _capacity_inputs(1.2, ("draft", "live"))
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1),
        selections=selections,
    )
    unscoped = [
        item for item in _rules(root) if item.rule == "role_over_allocated"
    ]
    scoped = [
        item
        for item in _rules(root, "sel-a")
        if item.rule == "role_over_allocated"
    ]
    assert unscoped == []
    assert len(scoped) == 1
    assert scoped[0].section == "sel-a"


def test_role_capacity_message_names_role_period_and_sorted_contributors(
    make_portfolio,
):
    menu, selections = _capacity_inputs(1.2)
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1),
        selections=selections,
    )
    hit = next(
        item for item in _rules(root) if item.rule == "role_over_allocated"
    )
    assert "Role 'Analyst' in Y1" in hit.message
    assert "1.2 FTE versus capacity 1 FTE" in hit.message
    assert hit.message.index("sel-a") < hit.message.index("sel-b")


def test_role_capacity_counts_roster_base_unscaled_by_funder_share(
    make_portfolio,
):
    menu = _v1_menu()
    menu["items"][2]["resourcing"]["roster"][0]["fte"] = 0.75
    selections = [
        _selection(
            "sel-base",
            "plain-a",
            fraction=0,
            status="live",
            horizon=12,
            org_base=True,
        )
    ]
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=0.7),
        selections=selections,
    )
    hit = next(
        item for item in _rules(root) if item.rule == "role_over_allocated"
    )
    assert "0.75 FTE versus capacity 0.7 FTE" in hit.message


def test_role_capacity_sums_multiple_roster_entries_for_one_role(
    make_portfolio,
):
    menu = _v1_menu()
    menu["items"][2]["resourcing"]["roster"] = [
        {"role": "Analyst", "fte": 0.75, "months": 12},
        {"role": "Analyst", "fte": 0.5, "months": 12},
    ]
    selections = [
        _selection(
            "sel-base",
            "plain-a",
            fraction=0,
            status="live",
            horizon=12,
            org_base=True,
        )
    ]
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1.2),
        selections=selections,
    )
    hit = next(
        item for item in _rules(root) if item.rule == "role_over_allocated"
    )
    assert "1.25 FTE versus capacity 1.2 FTE" in hit.message


def test_every_roster_entry_role_must_resolve(make_portfolio):
    menu = _v1_menu()
    menu["items"][2]["resourcing"]["roster"].append(
        {"role": "Missing role", "fte": 0.25, "months": 12}
    )
    root = _v1_root(make_portfolio, menu=menu)
    hits = [
        item
        for item in run_gates(load_portfolio(root))
        if item.rule == "unknown_role"
    ]
    assert len(hits) == 1
    assert "Missing role" in hits[0].message


def test_role_capacity_counts_shared_roster_base_once(make_portfolio):
    menu = _v1_menu()
    menu["items"][2]["resourcing"]["roster"][0]["fte"] = 1.0
    selections = [
        _selection(
            "sel-a",
            "plain-a",
            fraction=0,
            status="live",
            horizon=12,
            org_base=True,
        ),
        _selection(
            "sel-b",
            "plain-b",
            fraction=0,
            status="live",
            horizon=12,
            org_base=True,
        ),
    ]
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1),
        selections=selections,
    )

    hits = [
        item for item in _rules(root) if item.rule == "role_over_allocated"
    ]

    assert hits == []


def test_role_capacity_adds_incremental_demand_to_shared_roster_base(
    make_portfolio,
):
    menu = _v1_menu()
    menu["items"][2]["resourcing"]["roster"][0]["fte"] = 1.0
    selections = [
        _selection(
            "sel-a",
            "plain-a",
            fraction=0.5,
            status="live",
            horizon=12,
            org_base=True,
        ),
        _selection(
            "sel-b",
            "plain-b",
            fraction=0.5,
            status="live",
            horizon=12,
            org_base=True,
        ),
    ]
    root = _v1_root(
        make_portfolio,
        menu=menu,
        rates=_v1_rates(capacity=1),
        selections=selections,
    )

    hits = [
        item for item in _rules(root) if item.rule == "role_over_allocated"
    ]

    assert len(hits) == 1
    assert "1.5 FTE versus capacity 1 FTE" in hits[0].message


# -- outside-window warnings and estimate carriage ---------------------


@pytest.mark.parametrize(
    ("amount", "start", "duration", "fraction", "warns"),
    [
        (2.0, 11, 2, 1.0, False),
        (2.0000002, 11, 2, 1.0, True),
        (1.0, 12, 1, 1.0, False),
        (1.000001, 12, 1, 1.0, True),
        (100.0, 0, 12, 1.0, False),
        (100.0, 12, 1, 0.0, False),
    ],
)
def test_phase_outside_window_warns_only_above_one_dollar(
    make_portfolio, amount, start, duration, fraction, warns
):
    menu = _v1_menu()
    item = menu["items"][3]
    item["duration_months"] = duration
    item["resourcing"] = {
        "amount_usd": amount,
        "overhead_included": True,
    }
    selection = _selection(
        "sel-outside",
        "plain-a",
        fraction=fraction,
        status="live",
        horizon=12,
        start=start,
    )
    root = _v1_root(make_portfolio, menu=menu, selections=[selection])
    hits = [
        item for item in _rules(root) if item.rule == "phase_outside_window"
    ]
    assert bool(hits) is warns


def test_json_carries_every_encountered_estimate_with_metadata(
    make_portfolio,
):
    result = _invoke(
        "--selection", "sel-alpha", "--json", _v1_root(make_portfolio)
    )
    assert result.exit_code == 0, result.output
    estimates = json.loads(result.stdout)["estimates"]
    assert estimates["menu.unit_costs.token.usd_per_unit"] == _estimate(
        3, 2, 4
    )
    assert estimates["rates.roles.Analyst.loaded_usd"] == _estimate(
        120000, 100000, 140000
    )
    assert any(path.endswith("amount_usd.0.const") for path in estimates)
    assert any(path.endswith("amount_usd.1.per.count") for path in estimates)
    assert any(path.endswith("revenue.0.price_usd") for path in estimates)


def test_all_json_carries_estimates_independently_per_selection(
    make_portfolio,
):
    result = _invoke("--all", "--json", _v1_root(make_portfolio))
    assert result.exit_code == 0
    selections = json.loads(result.stdout)["selections"]
    alpha = selections["sel-alpha"]["estimates"]
    zeta = selections["sel-zeta"]["estimates"]
    assert "menu.unit_costs.token.usd_per_unit" in alpha
    assert "rates.roles.Analyst.loaded_usd" in alpha
    assert "rates.roles.Analyst.loaded_usd" in zeta
    assert "menu.unit_costs.token.usd_per_unit" not in zeta


def test_zero_duration_kind_result_compiles(make_portfolio):
    menu = _v1_menu()
    menu["kinds"]["widget"]["duration_months"] = 0
    selection = _selection("sel-zero-kind", "kind-z", horizon=12)
    root = _v1_root(
        make_portfolio,
        menu=menu,
        selections=[selection],
    )
    findings = run_gates(load_portfolio(root))
    assert not any(item.level == "error" for item in findings)

    result = _invoke("--selection", "sel-zero-kind", "--json", root)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["items"][0]["duration_months"] == 0
    assert payload["periods"][0]["cost"]["total"] == pytest.approx(
        payload["total_usd"]
    )


def test_zero_duration_inline_instance_compiles(make_portfolio):
    selection = _selection("sel-inline", "plain-a")
    selection["selections"] = [
        {
            "instance": {
                "id": "inline-zero",
                "kind": "widget",
                "params": {"count": 1},
                "duration_months": 0,
            },
            "fraction": 1.0,
        }
    ]
    root = _v1_root(make_portfolio, selections=[selection])
    findings = run_gates(load_portfolio(root), "sel-inline")
    assert not any(item.level == "error" for item in findings)

    result = _invoke("--selection", "sel-inline", "--json", root)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["items"][0]["duration_months"] == 0
