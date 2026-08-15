"""Resolver and compiler tests for the v1 parametric budget model.

The arithmetic expectations in this module are deliberately hand-computed.
The fixed-seed phasing matrix exercises conservation over work which starts
before, within, and after the selection window without adding Hypothesis as a
project dependency.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import pytest

from grantkit.menu import (
    Menu,
    Portfolio,
    Rates,
    Selection,
    evaluate_form,
    item_cost,
    resolve_item,
    selection_cost,
)


def _estimate(
    central: float,
    low: float | None = None,
    high: float | None = None,
    basis: str = "assumed",
    source: str = "synthetic estimate",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "central": central,
        "basis": basis,
        "source": source,
    }
    if low is not None:
        result["low"] = low
    if high is not None:
        result["high"] = high
    return result


def _rates(*, lead: Any = 120000, analyst: Any = 60000) -> dict[str, Any]:
    return {
        "schema": "grantkit-rates/v1",
        "provider": "synthetic-rates 1.0",
        "generated": "2026-08-15",
        "currency": "USD",
        "roles": [
            {"role": "Lead", "loaded_usd": lead},
            {"role": "Analyst", "loaded_usd": analyst},
        ],
    }


def _item(
    item_id: str = "work",
    *,
    resourcing: dict[str, Any] | None = None,
    duration: int | None = 1,
    kind: str | None = None,
    params: dict[str, Any] | None = None,
    revenue: list[dict[str, Any]] | None = None,
    item_type: str = "program",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": item_id,
        "type": item_type,
        "title": f"{item_id} title",
        "what": "Synthetic work.",
        "evidence": "Synthetic evidence.",
        "status": "planned",
        "dependencies": [],
        "provenance": ["synthetic"],
        "resourcing": resourcing or {"amount_usd": 0.0},
    }
    if duration is not None:
        result["duration_months"] = duration
    if kind is not None:
        result["kind"] = kind
    if params is not None:
        result["params"] = params
    if revenue is not None:
        result["revenue"] = revenue
    return result


def _menu(
    items: list[dict[str, Any]],
    *,
    kinds: dict[str, Any] | None = None,
    unit_price: Any = 1.25,
    overhead: float = 0.0,
    presets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "grantkit-menu/v1",
        "currency": "USD",
        "overheads": {"fiscal_sponsorship_rate": overhead},
        "unit_costs": {
            "widget": {
                "usd_per_unit": unit_price,
                "provenance": ["synthetic"],
            },
            "other": {
                "usd_per_unit": 2.0,
                "provenance": ["synthetic"],
            },
        },
        "items": items,
    }
    if kinds is not None:
        result["kinds"] = kinds
    if presets is not None:
        result["kind_presets"] = presets
    return result


def _selection(
    lines: list[dict[str, Any]],
    *,
    window: int = 12,
    horizon: int | None = None,
    org_base: dict[str, Any] | None = None,
    selection_id: str = "proposal",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "grantkit-selection/v1",
        "id": selection_id,
        "funder": "Synthetic funder",
        "status": "draft",
        "window_months": window,
        "selections": lines,
    }
    if horizon is not None:
        result["horizon_months"] = horizon
    if org_base is not None:
        result["org_base"] = org_base
    return result


def _portfolio(
    menu_data: dict[str, Any],
    selection_data: dict[str, Any],
    rates_data: dict[str, Any] | None = None,
) -> Portfolio:
    rates_data = rates_data or _rates()
    return Portfolio(
        root=Path("/synthetic/v1-engine-tests"),
        menu_data=menu_data,
        rates_data=rates_data,
        selections_data=[selection_data],
        menu=Menu.from_dict(menu_data),
        rates=Rates.from_dict(rates_data),
        selections=[Selection.from_dict(selection_data)],
    )


def _compile(
    menu_data: dict[str, Any],
    selection_data: dict[str, Any],
    rates_data: dict[str, Any] | None = None,
):
    portfolio = _portfolio(menu_data, selection_data, rates_data)
    return selection_cost(portfolio.selections[0], portfolio)


# -- FORM evaluation ---------------------------------------------------


@pytest.mark.parametrize(
    ("form", "params", "expected"),
    [
        (7, {}, 7.0),
        (2.5, {}, 2.5),
        (_estimate(4.25, 4.0, 5.0), {}, 4.25),
        ({"const": 4}, {}, 4.0),
        ({"per": {"n": 2}}, {"n": 3}, 6.0),
        ({"const": 1, "per": {"n": 2}}, {"n": 3}, 7.0),
        ({"per": {"n": 2, "m": 0.5}}, {"n": 3, "m": 4}, 8.0),
        ({"by": {"tier": {"basic": 2, "full": 8}}}, {"tier": "full"}, 8),
        ({"by": {"tier": {"basic": 2}}}, {"tier": "full"}, 0.0),
        (
            {"const": 3, "by": {"tier": {"basic": 2}}},
            {"tier": "full"},
            3.0,
        ),
        ({"const": 5, "when": {"tier": ["full"]}}, {"tier": "full"}, 5),
        ({"const": 5, "when": {"tier": ["full"]}}, {"tier": "basic"}, 0),
        ({"const": 5, "when": {"flag": [True]}}, {"flag": True}, 5),
        ({"const": 5, "when": {"flag": [1]}}, {"flag": True}, 0),
        ({"const": 5, "when": {"flag": [False]}}, {"flag": False}, 5),
        ([1, {"const": 2}, {"per": {"n": 3}}], {"n": 4}, 15),
        ([[1, 2], [{"const": 3}, 4]], {}, 10),
        (
            {
                "const": _estimate(1.5),
                "per": {"n": _estimate(2.25)},
                "by": {"tier": {"full": _estimate(3.5)}},
            },
            {"n": 2, "tier": "full"},
            9.5,
        ),
        (
            {"by": {"a": {"x": 2}, "b": {"y": 3}}},
            {"a": "x", "b": "y"},
            5,
        ),
        (
            {"const": 9, "when": {"tier": ["full"], "flag": [True]}},
            {"tier": "full", "flag": True},
            9,
        ),
        (
            {"const": 9, "when": {"tier": ["full"], "flag": [True]}},
            {"tier": "full", "flag": False},
            0,
        ),
        ({"by": {"flag": {True: 4, False: 7}}}, {"flag": False}, 7),
    ],
)
def test_evaluate_form_operations(form, params, expected):
    assert evaluate_form(form, params) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("form", "params", "message"),
    [
        ({"wat": 1}, {}, "unknown FORM keys"),
        ({"per": {"missing": 1}}, {}, "unknown parameter"),
        ({"per": {"name": 1}}, {"name": "not numeric"}, "must be a number"),
        ({"when": {"missing": [1]}}, {}, "unknown parameter"),
        ({"when": {"flag": True}}, {"flag": True}, "must be a list"),
        ({"by": {"missing": {"x": 1}}}, {}, "unknown parameter"),
        ({"per": []}, {}, "must be a mapping"),
        ({"central": -1, "basis": "assumed"}, {}, "invalid"),
    ],
)
def test_evaluate_form_rejects_malformed_inputs(form, params, message):
    with pytest.raises(ValueError, match=message):
        evaluate_form(form, params)


def test_estimates_are_collected_with_stable_dotted_paths():
    estimates: dict[str, Any] = {}
    form = [
        {"const": _estimate(2, 1, 3, "configured", "first")},
        {
            "per": {"n": _estimate(4, 3, 5)},
            "when": {"enabled": [False]},
        },
    ]
    assert evaluate_form(form, {"n": 10, "enabled": True}, estimates, "x") == 2
    assert list(estimates) == ["x.0.const", "x.1.per.n"]
    assert estimates["x.0.const"] == {
        "central": 2,
        "low": 1,
        "high": 3,
        "basis": "configured",
        "source": "first",
    }
    # Inactive alternatives are still uncertainty metadata.
    assert estimates["x.1.per.n"]["central"] == 4


def test_form_list_sums_left_to_right_without_rounding():
    assert evaluate_form([1e16, 1.0, 1.0], {}) == 1e16
    assert evaluate_form([1.0, 1.0, 1e16], {}) == 1.0000000000000002e16


# -- kind resolution ---------------------------------------------------


def _service_kind() -> dict[str, Any]:
    return {
        "title": "Service",
        "doc": "Parametric service.",
        "params": {
            "modules_per_region": {
                "type": "number",
                "min": 0,
                "default": 10,
            },
            "regions": {"type": "integer", "min": 1, "default": 2},
            "tier": {
                "type": "enum",
                "values": ["basic", "full"],
                "default": "basic",
            },
            "label": {"type": "string", "default": "Default"},
        },
        "derived": {
            "modules": {"product": ["modules_per_region", "regions"]},
            "units_plus_one": {"sum": ["modules", 1]},
            "double_units": {"product": ["units_plus_one", 2]},
        },
        "resourcing": {
            "fte_months": {
                "Lead": {"per": {"regions": 0.5}},
                "Analyst": {
                    "per": {"modules": 0.25},
                    "when": {"tier": ["full"]},
                },
            },
            "units": {"widget": {"per": {"double_units": 1}}},
            "contract_usd": {"const": 100},
        },
        "duration_months": [
            {"const": 1},
            {"per": {"regions": 0.5}},
        ],
        "dependencies": {"by": {"tier": {"full": ["quality-ladder"]}}},
        "revenue": [
            {
                "stream": "kind-stream",
                "price_usd": {"const": 2},
                "volume_per_year": [{"per": {"modules": 1}}],
                "starts": "completion",
            }
        ],
        "title_template": "{label} {tier}, {regions} regions",
        "provenance": ["kind source"],
    }


def test_kind_resolution_uses_defaults_and_declaration_order():
    resolved = resolve_item(
        {"id": "default-service", "kind": "service"},
        {"service": _service_kind()},
    )
    assert resolved.params == {
        "modules_per_region": 10,
        "regions": 2,
        "tier": "basic",
        "label": "Default",
    }
    assert resolved.derived == {
        "modules": 20.0,
        "units_plus_one": 21.0,
        "double_units": 42.0,
    }
    assert resolved.resourcing.units == {"widget": 42.0}
    assert resolved.duration_months == pytest.approx(2.0)


def test_kind_resolution_applies_params_to_forms_and_title():
    resolved = resolve_item(
        {
            "id": "full-service",
            "kind": "service",
            "params": {
                "modules_per_region": 4,
                "regions": 3,
                "tier": "full",
                "label": "SNAP",
            },
        },
        {"service": _service_kind()},
    )
    assert resolved.title == "SNAP full, 3 regions"
    assert resolved.resourcing.fte_months == {
        "Lead": pytest.approx(1.5),
        "Analyst": pytest.approx(3.0),
    }
    assert resolved.resourcing.units == {"widget": pytest.approx(26.0)}
    assert resolved.dependencies == ["quality-ladder"]
    assert resolved.revenue[0].volume_per_year == [pytest.approx(12.0)]


def test_derived_forward_reference_fails_in_declaration_order():
    kind = _service_kind()
    kind["derived"] = {
        "too_early": {"sum": ["later", 1]},
        "later": {"sum": [1, 2]},
    }
    with pytest.raises(ValueError, match="unknown value 'later'"):
        resolve_item({"id": "bad", "kind": "service"}, {"service": kind})


def test_explicit_resourcing_deep_merges_role_and_unit_leaves():
    kind = _service_kind()
    kind["resourcing"].update(
        {
            "units": {"widget": 2, "other": 3},
            "recurring_usd_per_year": 200,
            "amount_usd": 300,
        }
    )
    resolved = resolve_item(
        {
            "id": "override",
            "kind": "service",
            "params": {"tier": "full"},
            "resourcing": {
                "fte_months": {"Lead": 9},
                "units": {"widget": 7},
                "contract_usd": 110,
                "overhead_included": True,
            },
        },
        {"service": kind},
    )
    assert resolved.resourcing.fte_months == {
        "Lead": pytest.approx(9.0),
        "Analyst": pytest.approx(5.0),
    }
    assert resolved.resourcing.units == {
        "widget": pytest.approx(7.0),
        "other": pytest.approx(3.0),
    }
    assert resolved.resourcing.contract_usd == pytest.approx(110.0)
    assert resolved.resourcing.recurring_usd_per_year == pytest.approx(200.0)
    assert resolved.resourcing.amount_usd == pytest.approx(300.0)
    assert resolved.resourcing.overhead_included is True


def test_explicit_dependencies_are_stably_unioned_with_kind_dependencies():
    resolved = resolve_item(
        {
            "id": "deps",
            "kind": "service",
            "params": {"tier": "full"},
            "dependencies": ["quality-ladder", "explicit-dependency"],
        },
        {"service": _service_kind()},
    )
    assert resolved.dependencies == ["quality-ladder", "explicit-dependency"]


@pytest.mark.parametrize(
    ("explicit_revenue", "expected_streams"),
    [
        ([], []),
        (
            [
                {
                    "stream": "replacement",
                    "price_usd": 3,
                    "volume_per_year": [4],
                }
            ],
            ["replacement"],
        ),
    ],
)
def test_explicit_revenue_replaces_the_kind_list(
    explicit_revenue, expected_streams
):
    resolved = resolve_item(
        {
            "id": "revenue-override",
            "kind": "service",
            "revenue": explicit_revenue,
        },
        {"service": _service_kind()},
    )
    assert [stream.stream for stream in resolved.revenue] == expected_streams


def test_explicit_title_duration_and_provenance_precedence():
    resolved = resolve_item(
        {
            "id": "metadata",
            "kind": "service",
            "title": "Explicit title",
            "duration_months": 8,
            "provenance": ["kind source", "item source"],
        },
        {"service": _service_kind()},
    )
    assert resolved.title == "Explicit title"
    assert resolved.duration_months == 8.0
    assert resolved.provenance == ["kind source", "item source"]


def test_kind_presets_remain_pure_data_on_parsed_menu():
    preset = {
        "kind": "service",
        "title": "SNAP starter",
        "params": {"label": "SNAP", "regions": 10},
    }
    menu = Menu.from_dict(
        _menu(
            [_item()],
            kinds={"service": _service_kind()},
            presets={"snap": preset},
        )
    )
    assert menu.kind_presets["snap"].raw == preset
    assert menu.kind_presets["snap"].params == {
        "label": "SNAP",
        "regions": 10,
    }


def test_inline_instance_compiles_as_planned_kind_item():
    selection = _selection(
        [
            {
                "instance": {
                    "id": "inline-full",
                    "kind": "service",
                    "params": {
                        "modules_per_region": 4,
                        "regions": 3,
                        "tier": "full",
                        "label": "Inline",
                    },
                    "title": "Private inline service",
                },
                "fraction": 0.5,
                "start_month": 2,
            }
        ]
    )
    cost = _compile(_menu([], kinds={"service": _service_kind()}), selection)
    line = cost.items[0]
    assert line.item_id == "inline-full"
    assert line.title == "Private inline service"
    assert line.resolved is not None
    assert line.resolved.status == "planned"
    assert line.resolved.evidence == ""
    assert line.start_month == 2
    assert line.item.units_usd == pytest.approx(26 * 1.25)
    assert line.one_time_usd == pytest.approx(line.item.one_time_usd * 0.5)


# -- estimates through compilation ------------------------------------


def test_compiler_uses_estimate_central_values_and_collects_every_path():
    kind = {
        "params": {"n": {"type": "number", "default": 2}},
        "resourcing": {
            "fte_months": {"Lead": {"per": {"n": _estimate(1.5, 1, 2)}}},
            "units": {"widget": {"per": {"n": 3}}},
        },
        "duration_months": 1,
        "revenue": [
            {
                "stream": "estimated-sales",
                "price_usd": _estimate(1.25, 1, 2),
                "volume_per_year": [_estimate(1200, 600, 1800)],
                "starts": "start",
            }
        ],
    }
    item = _item(
        kind="service",
        duration=None,
        resourcing={"contract_usd": _estimate(10.25, 5, 15)},
    )
    menu = _menu(
        [item],
        kinds={"service": kind},
        unit_price=_estimate(2.5, 2, 3, "configured"),
    )
    rates = _rates(lead=_estimate(120000, 100000, 140000, "computed"))
    cost = _compile(menu, _selection([{"item": "work", "fraction": 1}]), rates)
    assert cost.labor_usd == pytest.approx(30000.0)
    assert cost.units_usd == pytest.approx(15.0)
    assert cost.contract_usd == pytest.approx(10.25)
    assert set(cost.estimates) == {
        "kinds.service.resourcing.fte_months.Lead.per.n",
        "kinds.service.revenue.0.price_usd",
        "kinds.service.revenue.0.volume_per_year.0",
        "menu.items.work.resourcing.contract_usd",
        "menu.unit_costs.widget.usd_per_unit",
        "rates.roles.Lead.loaded_usd",
    }
    assert cost.estimates["rates.roles.Lead.loaded_usd"]["central"] == 120000
    assert cost.estimates["menu.unit_costs.widget.usd_per_unit"]["low"] == 2


def test_compiled_estimates_are_sorted_in_structured_output():
    item = _item(
        resourcing={
            "contract_usd": _estimate(2),
            "amount_usd": _estimate(3),
        }
    )
    cost = _compile(
        _menu([item]), _selection([{"item": "work", "fraction": 1}])
    )
    payload = cost.to_dict()
    assert list(payload["estimates"]) == sorted(payload["estimates"])


def test_used_rate_carries_nested_estimates_into_compiled_metadata():
    rates = _rates(lead=_estimate(120000, 100000, 140000, "computed"))
    rates["roles"][0].update(
        {
            "base_usd": _estimate(90000, 80000, 100000),
            "components": [
                {
                    "name": "benefits",
                    "amount_usd": _estimate(30000, 20000, 40000),
                    "basis": "configured",
                }
            ],
        }
    )
    item = _item(resourcing={"fte_months": {"Lead": 1}})
    cost = _compile(
        _menu([item]),
        _selection([{"item": "work", "fraction": 1}]),
        rates,
    )
    assert {
        "rates.roles.Lead.loaded_usd",
        "rates.roles.Lead.base_usd",
        "rates.roles.Lead.components.0.amount_usd",
    } <= set(cost.estimates)


# -- revenue -----------------------------------------------------------


def _compile_revenue(
    stream: dict[str, Any],
    *,
    fraction: float = 1.0,
    duration: int = 1,
    start: int = 0,
    window: int = 12,
    horizon: int = 12,
):
    item = _item(
        resourcing={"amount_usd": 1.0},
        duration=duration,
        revenue=[stream],
    )
    selection = _selection(
        [{"item": "work", "fraction": fraction, "start_month": start}],
        window=window,
        horizon=horizon,
    )
    return _compile(_menu([item]), selection)


@pytest.mark.parametrize(
    ("starts", "duration", "horizon", "expected"),
    [
        ("start", 3, 12, 2400.0),
        ("completion", 3, 12, 1800.0),
        ("completion", 12, 12, 0.0),
        ("start", 3, 6, 1200.0),
    ],
)
def test_revenue_start_and_completion_timing(
    starts, duration, horizon, expected
):
    cost = _compile_revenue(
        {
            "stream": "sales",
            "price_usd": 2,
            "volume_per_year": [1200],
            "starts": starts,
        },
        duration=duration,
        horizon=horizon,
    )
    assert cost.revenue["enabled_total"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("horizon", "ramp", "expected"),
    [
        (12, 6, 900.0),
        (6, 12, 150.0),
        (12, 0, 1200.0),
        (3, 6, 75.0),
    ],
)
def test_revenue_ramp_uses_continuous_analytic_months(horizon, ramp, expected):
    cost = _compile_revenue(
        {
            "stream": "ramped",
            "price_usd": 1,
            "volume_per_year": [1200],
            "starts": "start",
            "ramp_months": ramp,
        },
        horizon=horizon,
    )
    assert cost.revenue["enabled_total"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("horizon", "expected"),
    [(12, 120.0), (24, 360.0), (30, 480.0), (36, 600.0), (48, 840.0)],
)
def test_revenue_year_vector_persists_the_last_volume(horizon, expected):
    cost = _compile_revenue(
        {
            "stream": "growth",
            "price_usd": 1,
            "volume_per_year": [120, 240],
            "starts": "start",
        },
        horizon=horizon,
    )
    assert cost.revenue["enabled_total"] == pytest.approx(expected)


def test_revenue_start_month_offsets_the_year_vector():
    cost = _compile_revenue(
        {
            "stream": "delayed",
            "price_usd": 1,
            "volume_per_year": [120, 240],
            "starts": "start",
        },
        start=6,
        horizon=24,
    )
    assert cost.revenue["enabled_total"] == pytest.approx(240.0)


@pytest.mark.parametrize(
    ("fraction", "enabled", "attributed"),
    [
        (1.0, 1200.0, 1200.0),
        (0.5, 1200.0, 600.0),
        (0.01, 1200.0, 12.0),
        (0.0, 0.0, 0.0),
    ],
)
def test_revenue_enabled_and_attributed_fraction_semantics(
    fraction, enabled, attributed
):
    cost = _compile_revenue(
        {
            "stream": "fractional",
            "price_usd": 1,
            "volume_per_year": [1200],
            "starts": "start",
        },
        fraction=fraction,
    )
    assert cost.revenue["enabled_total"] == pytest.approx(enabled)
    assert cost.revenue["attributed_total"] == pytest.approx(attributed)
    assert cost.net_of_attributed_usd == pytest.approx(
        cost.total_usd - attributed
    )


def test_revenue_periods_and_stream_totals_reconcile():
    cost = _compile_revenue(
        {
            "stream": "periodized",
            "price_usd": 2,
            "volume_per_year": [120, 240],
            "starts": "start",
            "ramp_months": 6,
        },
        fraction=0.25,
        horizon=30,
    )
    stream = cost.revenue["by_stream"][0]
    assert sum(
        row["enabled_usd"] for row in stream["by_period"]
    ) == pytest.approx(stream["enabled_usd"])
    assert sum(
        row["attributed_usd"] for row in cost.revenue["by_period"]
    ) == pytest.approx(cost.revenue["attributed_total"])
    assert [period["revenue"]["enabled"] for period in cost.periods] == [
        pytest.approx(row["enabled_usd"]) for row in cost.revenue["by_period"]
    ]


def test_revenue_estimate_basis_and_assumed_marker_are_reported():
    cost = _compile_revenue(
        {
            "stream": "estimated",
            "price_usd": _estimate(2, 1, 3, "configured"),
            "volume_per_year": [_estimate(120, 60, 180, "assumed")],
            "starts": "start",
        }
    )
    stream = cost.revenue["by_stream"][0]
    assert stream["basis"] == "configured"
    assert stream["assumed"] is True


# -- phasing, staffing, roster, and float semantics -------------------


def test_roster_org_base_arithmetic_and_unscaled_base_fte():
    org = _item(
        "org",
        item_type="org-base",
        duration=24,
        resourcing={
            "roster": [
                {"role": "Lead", "fte": 1.0, "months": 18},
                {"role": "Analyst", "fte": 0.5},
            ],
            "non_personnel_usd_per_year": 120000,
        },
    )
    cost = _compile(
        _menu([org], overhead=0.1),
        _selection(
            [],
            window=12,
            horizon=12,
            org_base={"item": "org", "fraction": 0.25},
        ),
    )
    assert cost.org_base_usd == pytest.approx(120000.0)
    assert cost.overhead_usd == pytest.approx(12000.0)
    assert [p["cost"]["org_base"] for p in cost.periods] == [
        pytest.approx(67500.0),
        pytest.approx(52500.0),
    ]
    assert cost.periods[0]["base_fte_by_role"] == {
        "Lead": pytest.approx(1.0),
        "Analyst": pytest.approx(0.5),
    }
    # Base staffing is the full org, not the funder's 25 percent share.
    assert cost.periods[1]["base_fte_by_role"] == {
        "Lead": pytest.approx(0.5),
        "Analyst": pytest.approx(0.5),
    }


def test_roster_overhead_included_excludes_labor_and_non_personnel():
    org = _item(
        "org",
        item_type="org-base",
        duration=12,
        resourcing={
            "roster": [{"role": "Lead", "fte": 1.0}],
            "non_personnel_usd_per_year": 12000,
            "overhead_included": True,
        },
    )
    cost = _compile(
        _menu([org], overhead=0.1),
        _selection(
            [],
            org_base={"item": "org", "fraction": 0.5},
        ),
    )
    assert cost.org_base_usd == pytest.approx(66000.0)
    assert cost.overhead_usd == 0.0
    assert sum(period["cost"]["overhead"] for period in cost.periods) == 0.0


def test_item_cost_reports_roster_and_non_personnel_components():
    item = _item(
        duration=6,
        resourcing={
            "roster": [{"role": "Lead", "fte": 0.5}],
            "non_personnel_usd_per_year": 24000,
        },
    )
    portfolio = _portfolio(
        _menu([item]), _selection([{"item": "work", "fraction": 1}])
    )
    resolved = resolve_item(portfolio.menu.items[0], portfolio.menu.kinds)
    cost = item_cost(resolved, portfolio.rates, portfolio.menu.unit_costs)
    assert cost.labor_usd == pytest.approx(30000.0)
    assert cost.contract_usd == pytest.approx(12000.0)
    assert cost.to_dict()["roster_by_role"]["Lead"] == {
        "fte": pytest.approx(0.5),
        "months": pytest.approx(3.0),
        "usd": pytest.approx(30000.0),
    }


def test_incremental_staffing_is_fraction_weighted_and_time_phased():
    kind = {
        "params": {},
        "resourcing": {"fte_months": {"Lead": 18}},
        "duration_months": 18,
    }
    item = _item(kind="long", duration=None)
    cost = _compile(
        _menu([item], kinds={"long": kind}),
        _selection(
            [{"item": "work", "fraction": 0.5, "start_month": 6}],
            window=24,
            horizon=24,
        ),
    )
    assert [period["cost"]["labor"] for period in cost.periods] == [
        pytest.approx(30000.0),
        pytest.approx(60000.0),
    ]
    assert [period["fte_by_role"]["Lead"] for period in cost.periods] == [
        pytest.approx(0.25),
        pytest.approx(0.5),
    ]


def test_period_categories_and_totals_reconcile_individually():
    item = _item(
        duration=18,
        resourcing={
            "fte_months": {"Lead": 6},
            "units": {"widget": 8},
            "contract_usd": 30,
            "amount_usd": 40,
            "recurring_usd_per_year": 120,
        },
    )
    cost = _compile(
        _menu([item], overhead=0.1),
        _selection(
            [{"item": "work", "fraction": 0.25, "start_month": 3}],
            window=18,
            horizon=18,
        ),
    )
    expected = {
        "labor": cost.labor_usd,
        "units": cost.units_usd,
        "contract": cost.contract_usd,
        "flat": cost.flat_usd,
        "recurring": cost.recurring_usd,
        "org_base": cost.org_base_usd,
        "overhead": cost.overhead_usd,
    }
    for category, total in expected.items():
        assert sum(p["cost"][category] for p in cost.periods) == pytest.approx(
            total, abs=1e-9
        )
    for period in cost.periods:
        assert period["cost"]["total"] == pytest.approx(
            sum(period["cost"][name] for name in expected)
        )


def test_work_outside_window_is_reported_but_not_dropped():
    item = _item(duration=6, resourcing={"contract_usd": 120})
    cost = _compile(
        _menu([item], overhead=0.1),
        _selection(
            [{"item": "work", "fraction": 1, "start_month": 9}],
            window=12,
            horizon=12,
        ),
    )
    assert cost.total_usd == pytest.approx(132.0)
    assert sum(p["cost"]["total"] for p in cost.periods) == pytest.approx(
        132.0
    )
    assert cost.items[0].outside_window_usd == pytest.approx(66.0)
    assert cost.outside_window_usd == pytest.approx(66.0)


def test_recurring_uses_window_while_revenue_uses_horizon():
    item = _item(
        resourcing={"recurring_usd_per_year": 1200},
        revenue=[
            {
                "stream": "sales",
                "price_usd": 1,
                "volume_per_year": [1200],
                "starts": "start",
            }
        ],
    )
    cost = _compile(
        _menu([item]),
        _selection(
            [{"item": "work", "fraction": 0.5}],
            window=6,
            horizon=24,
        ),
    )
    assert cost.recurring_usd == pytest.approx(300.0)
    assert cost.revenue["enabled_total"] == pytest.approx(2400.0)
    assert cost.revenue["attributed_total"] == pytest.approx(1200.0)


def test_money_remains_unrounded_ieee_float_until_render():
    item = _item(resourcing={"units": {"widget": 3}})
    cost = _compile(
        _menu([item], unit_price=0.1),
        _selection([{"item": "work", "fraction": 1}]),
    )
    assert cost.units_usd == 3 * 0.1
    assert cost.units_usd != 0.3
    assert cost.total_usd == 3 * 0.1


def test_zero_fraction_keeps_line_but_removes_cost_and_staffing():
    item = _item(resourcing={"fte_months": {"Lead": 12}})
    cost = _compile(
        _menu([item]),
        _selection([{"item": "work", "fraction": 0}]),
    )
    assert len(cost.items) == 1
    assert cost.items[0].funded_usd == 0.0
    assert cost.total_usd == 0.0
    assert cost.personnel == {}
    assert all(period["fte_by_role"] == {} for period in cost.periods)


# -- deterministic property-style phasing conservation ----------------


def _uniform_spread_cost(
    amount: float,
    start: float,
    duration: float,
    period_start: float,
    period_end: float,
) -> float:
    """Compute a test-only uniform allocation without engine helpers."""
    source_end = start + duration
    overlap = max(0.0, min(source_end, period_end) - max(start, period_start))
    return amount * overlap / duration


def _phasing_cases() -> list[tuple[int, int, float, int, int, float, bool]]:
    rng = random.Random(20260815)
    cases = []
    for index in range(128):
        start = rng.randrange(0, 61)
        duration = round(rng.uniform(0.125, 48.0), 6)
        window = rng.randrange(1, 49)
        horizon = rng.randrange(1, 61)
        fraction = round(rng.uniform(0.001, 1.0), 9)
        overhead_included = bool(index % 2)
        cases.append(
            (
                index,
                start,
                duration,
                window,
                horizon,
                fraction,
                overhead_included,
            )
        )
    return cases


@pytest.mark.parametrize(
    (
        "case_id",
        "start",
        "duration",
        "window",
        "horizon",
        "fraction",
        "overhead_included",
    ),
    _phasing_cases(),
)
def test_random_phasing_conserves_totals_and_categories(
    case_id,
    start,
    duration,
    window,
    horizon,
    fraction,
    overhead_included,
):
    kind = {
        "params": {},
        "resourcing": {
            "fte_months": {"Lead": 2.34567},
            "units": {"widget": 7.89123},
            "contract_usd": 1234.56789,
            "amount_usd": 765.43219,
            "recurring_usd_per_year": 333.33333,
            "overhead_included": overhead_included,
        },
        "duration_months": duration,
    }
    work = _item(f"work-{case_id}", kind="random-work", duration=None)
    work.pop("resourcing")
    base = _item(
        f"base-{case_id}",
        item_type="org-base",
        duration=1,
        resourcing={
            "amount_usd": 4321.09876,
            "overhead_included": overhead_included,
        },
    )
    selection = _selection(
        [
            {
                "item": f"work-{case_id}",
                "fraction": fraction,
                "start_month": start,
            }
        ],
        window=window,
        horizon=horizon,
        org_base={"item": f"base-{case_id}", "fraction": 0.137},
        selection_id=f"random-{case_id}",
    )
    cost = _compile(
        _menu(
            [work, base],
            kinds={"random-work": kind},
            unit_price=2.424,
            overhead=0.07,
        ),
        selection,
    )

    labor = fraction * 2.34567 / 12.0 * 120000.0
    units = fraction * 7.89123 * 2.424
    contract = fraction * 1234.56789
    flat = fraction * 765.43219
    recurring = fraction * 333.33333 * window / 12.0
    org_base = 0.137 * 4321.09876
    extent = max(float(window), float(horizon), start + duration)
    assert len(cost.periods) == max(1, math.ceil(extent / 12.0))

    for index, period in enumerate(cost.periods):
        period_start = float(index * 12)
        period_end = min(float((index + 1) * 12), extent)
        expected = {
            "labor": _uniform_spread_cost(
                labor, start, duration, period_start, period_end
            ),
            "units": _uniform_spread_cost(
                units, start, duration, period_start, period_end
            ),
            "contract": _uniform_spread_cost(
                contract, start, duration, period_start, period_end
            ),
            "flat": _uniform_spread_cost(
                flat, start, duration, period_start, period_end
            ),
            "recurring": _uniform_spread_cost(
                recurring, 0.0, float(window), period_start, period_end
            ),
            "org_base": _uniform_spread_cost(
                org_base, 0.0, float(window), period_start, period_end
            ),
        }
        overhead_bearing = (
            expected["labor"] + expected["units"] + expected["recurring"]
        )
        if not overhead_included:
            overhead_bearing += (
                expected["contract"] + expected["flat"] + expected["org_base"]
            )
        expected["overhead"] = 0.07 * overhead_bearing

        assert period["index"] == index
        assert period["label"] == f"Y{index + 1}"
        assert period["start_month"] == pytest.approx(period_start)
        assert period["months"] == pytest.approx(period_end - period_start)
        for category, expected_cost in expected.items():
            assert period["cost"][category] == pytest.approx(
                expected_cost, rel=0.0, abs=1e-6
            )
        assert period["cost"]["total"] == pytest.approx(
            sum(expected.values()), rel=0.0, abs=1e-6
        )

    assert sum(p["cost"]["total"] for p in cost.periods) == pytest.approx(
        cost.total_usd, rel=0.0, abs=1e-6
    )
