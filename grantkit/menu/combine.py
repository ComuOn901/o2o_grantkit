"""Deterministic rollups across several portfolio selections.

A combined budget is a planning view over several honest funder asks.  It
does not merge or rewrite those selections: funded dollars are summed,
shared menu-item fractions are stacked, and org-base fractions become a
coverage ledger with an explicit unclaimed gap.  Period staffing uses the
same convention as the capacity gate: incremental FTE sums, while a shared
org-base roster describes one organization and is counted once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .engine import SelectionCost, item_cost, selection_cost
from .gates import COFUNDING_TOLERANCE
from .resolve import resolve_item

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .loader import Portfolio


_CATEGORY_FIELDS = (
    "labor_usd",
    "units_usd",
    "contract_usd",
    "flat_usd",
    "recurring_usd",
    "org_base_usd",
    "overhead_usd",
)

_PERIOD_CATEGORIES = (
    "labor",
    "units",
    "contract",
    "flat",
    "recurring",
    "org_base",
    "overhead",
    "total",
)


@dataclass
class CombinedCost:
    """The compiled funding and operating rollup for several selections."""

    selection_ids: list[str]
    currency: str
    funders: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    org_bases: list[dict[str, Any]] = field(default_factory=list)
    personnel: dict[str, dict[str, float]] = field(default_factory=dict)
    categories: dict[str, float] = field(default_factory=dict)
    periods: list[dict[str, Any]] = field(default_factory=list)
    revenue: dict[str, Any] = field(default_factory=dict)
    outside_window_usd: float = 0.0
    net_of_attributed_usd: float = 0.0
    total_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a detached, JSON-ready representation."""
        return {
            "schema": "grantkit-combined-budget/v1",
            "selection_ids": list(self.selection_ids),
            "funders": [_copy_nested(entry) for entry in self.funders],
            "currency": self.currency,
            "items": [_copy_nested(entry) for entry in self.items],
            "org_bases": [_copy_nested(entry) for entry in self.org_bases],
            "personnel": {
                role: dict(self.personnel[role])
                for role in sorted(self.personnel)
            },
            "categories": {
                key: self.categories[key] for key in _CATEGORY_FIELDS
            },
            "periods": [_copy_nested(period) for period in self.periods],
            "revenue": _copy_nested(self.revenue),
            "outside_window_usd": self.outside_window_usd,
            "net_of_attributed_usd": self.net_of_attributed_usd,
            "total_usd": self.total_usd,
        }


def _copy_nested(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_nested(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_copy_nested(entry) for entry in value]
    return value


def _canonical_ids(selection_ids: list[str]) -> list[str]:
    if len(selection_ids) < 2:
        raise ValueError("A combined budget requires at least two selections")
    if len(set(selection_ids)) != len(selection_ids):
        raise ValueError("A combined budget cannot repeat a selection id")
    return sorted(selection_ids)


def compile_combined(
    portfolio: "Portfolio", selection_ids: list[str]
) -> CombinedCost:
    """Compile a deterministic rollup for two or more selections.

    The caller should run :func:`run_combined_gates` first.  Unknown ids
    raise ``KeyError`` and repeated/fewer-than-two ids raise ``ValueError``.
    Input order has no effect on the returned object.
    """
    ids = _canonical_ids(selection_ids)
    selections = []
    for selection_id in ids:
        selection = portfolio.get_selection(selection_id)
        if selection is None:
            raise KeyError(f"Unknown selection '{selection_id}'")
        selections.append(selection)

    costs = {
        selection.id: selection_cost(selection, portfolio)
        for selection in selections
    }
    result = CombinedCost(selection_ids=ids, currency=portfolio.menu.currency)
    result.funders = [
        {
            "selection_id": selection.id,
            "funder": selection.funder,
            "status": selection.status,
            "total_usd": costs[selection.id].total_usd,
        }
        for selection in selections
    ]
    result.items = _combine_items(selections, costs)
    result.org_bases = _combine_org_bases(portfolio, selections, costs)
    result.personnel = _combine_personnel(costs)
    result.categories = {
        field_name: sum(
            float(getattr(cost, field_name)) for cost in costs.values()
        )
        for field_name in _CATEGORY_FIELDS
    }
    result.periods = _combine_periods(selections, costs)
    result.revenue = _combine_revenue(selections, costs, result.periods)
    for index, period in enumerate(result.periods):
        revenue_period = result.revenue["by_period"][index]
        period["revenue"] = {
            "enabled": revenue_period["enabled_usd"],
            "attributed": revenue_period["attributed_usd"],
        }
    result.outside_window_usd = sum(
        cost.outside_window_usd for cost in costs.values()
    )
    result.total_usd = sum(cost.total_usd for cost in costs.values())
    result.net_of_attributed_usd = (
        result.total_usd - result.revenue["attributed_total"]
    )
    return result


def _combine_items(
    selections: list[Any], costs: dict[str, SelectionCost]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for selection in selections:
        cost = costs[selection.id]
        for source, line in zip(selection.selections, cost.items):
            # Inline instances are private to a selection and must never be
            # turned into a shared C2 claim merely because ids happen to
            # match in two proposal files.
            owner = selection.id if source.instance is not None else ""
            key = (owner, line.item_id)
            group = groups.setdefault(
                key,
                {
                    "item_id": line.item_id,
                    "title": line.title,
                    "type": line.type,
                    "shares": [],
                },
            )
            group["shares"].append(
                {
                    "selection_id": selection.id,
                    "funder": selection.funder,
                    "fraction": line.fraction,
                    "funded_usd": line.funded_usd,
                }
            )

    out: list[dict[str, Any]] = []
    for (owner, _), group in sorted(
        groups.items(), key=lambda pair: (pair[0][1], pair[0][0])
    ):
        shares = sorted(
            group["shares"], key=lambda entry: entry["selection_id"]
        )
        fraction = sum(float(share["fraction"]) for share in shares)
        out.append(
            {
                **{
                    key: value
                    for key, value in group.items()
                    if key != "shares"
                },
                "shares": shares,
                "fraction": fraction,
                "funded_usd": sum(
                    float(share["funded_usd"]) for share in shares
                ),
                "over_allocated": (
                    not owner and fraction > 1.0 + COFUNDING_TOLERANCE
                ),
            }
        )
    return out


def _combine_org_bases(
    portfolio: "Portfolio",
    selections: list[Any],
    costs: dict[str, SelectionCost],
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for selection in selections:
        cost = costs[selection.id]
        for source, line in zip(selection.selections, cost.items):
            # C2 treats a shared org-base menu item as the same claim whether
            # it appears as an ordinary selection line or via ``org_base``.
            # Inline instances remain selection-private, as in _combine_items.
            if source.instance is not None or line.type != "org-base":
                continue
            groups.setdefault(line.item_id, []).append(
                {
                    "kind": "selection",
                    "claim_kind": "item",
                    "selection_id": selection.id,
                    "funder": selection.funder,
                    "fraction": line.fraction,
                    "funded_usd": line.funded_usd,
                }
            )
        if selection.org_base is not None:
            groups.setdefault(selection.org_base.item, []).append(
                {
                    "kind": "selection",
                    "claim_kind": "org_base",
                    "selection_id": selection.id,
                    "funder": selection.funder,
                    "fraction": selection.org_base.fraction,
                    "funded_usd": cost.org_base_usd,
                }
            )

    out: list[dict[str, Any]] = []
    for item_id in sorted(groups):
        menu_item = portfolio.menu.items_by_id[item_id]
        resolved = resolve_item(
            menu_item,
            portfolio.menu.kinds,
            path=f"menu.items.{item_id}",
        )
        base_cost = item_cost(
            resolved, portfolio.rates, portfolio.menu.unit_costs
        )
        selection_shares = sorted(
            groups[item_id],
            key=lambda entry: (
                entry["selection_id"],
                0 if entry["claim_kind"] == "item" else 1,
            ),
        )
        coverage = sum(float(share["fraction"]) for share in selection_shares)
        gap = max(0.0, 1.0 - coverage)
        shares = [
            *selection_shares,
            {
                "kind": "gap",
                "claim_kind": "gap",
                "selection_id": None,
                "funder": "Unclaimed",
                "fraction": gap,
                "funded_usd": gap * base_cost.one_time_usd,
            },
        ]
        out.append(
            {
                "item_id": item_id,
                "title": resolved.title,
                "item_one_time_usd": base_cost.one_time_usd,
                "shares": shares,
                "coverage_fraction": coverage,
                "gap_fraction": gap,
                "over_allocated": (coverage > 1.0 + COFUNDING_TOLERANCE),
            }
        )
    return out


def _combine_personnel(
    costs: dict[str, SelectionCost],
) -> dict[str, dict[str, float]]:
    personnel: dict[str, dict[str, float]] = {}
    for cost in costs.values():
        for role, spend in cost.personnel.items():
            entry = personnel.setdefault(
                role,
                {
                    "fte_months": 0.0,
                    "loaded_usd": float(spend["loaded_usd"]),
                    "usd": 0.0,
                },
            )
            entry["fte_months"] += float(spend["fte_months"])
            entry["usd"] += float(spend["usd"])
    return {role: personnel[role] for role in sorted(personnel)}


def _overlap_months(
    start: float, end: float, period_start: float, period_end: float
) -> float:
    return max(0.0, min(end, period_end) - max(start, period_start))


def _combine_periods(
    selections: list[Any], costs: dict[str, SelectionCost]
) -> list[dict[str, Any]]:
    selections_by_id = {selection.id: selection for selection in selections}
    period_count = max(
        (len(cost.periods) for cost in costs.values()), default=0
    )
    periods: list[dict[str, Any]] = []
    for index in range(period_count):
        source_periods = [
            cost.periods[index]
            for cost in costs.values()
            if index < len(cost.periods)
        ]
        period_cost = {
            category: sum(
                float(period["cost"][category]) for period in source_periods
            )
            for category in _PERIOD_CATEGORIES
        }
        combined_months = max(
            float(period["months"]) for period in source_periods
        )
        incremental_fte_months: dict[str, float] = {}
        base_fte_months_by_item: dict[str, dict[str, float]] = {}
        for cost in costs.values():
            if index >= len(cost.periods):
                continue
            period = cost.periods[index]
            source_months = float(period["months"])
            source_incremental = {
                role: float(fte) * source_months
                for role, fte in period["fte_by_role"].items()
            }

            # When a shared org-base menu item is selected as an ordinary
            # line, the single-selection engine correctly treats its funded
            # roster as fraction-weighted attribution. Operationally, though,
            # that roster is still the same organization described by an
            # ``org_base`` claim. Remove the scaled roster from incremental
            # demand and add one unscaled candidate keyed by the shared item.
            selection = selections_by_id[cost.selection_id]
            period_start = float(period["start_month"])
            period_end = period_start + source_months
            for source, line in zip(selection.selections, cost.items):
                if (
                    source.instance is not None
                    or line.type != "org-base"
                    or line.fraction <= 0
                ):
                    continue
                route_fte_months: dict[str, float] = {}
                for roster in line.item.roster_lines:
                    active = float(roster["months"])
                    if active <= 0:
                        continue
                    start = float(line.start_month)
                    overlap = _overlap_months(
                        start,
                        start + active,
                        period_start,
                        period_end,
                    )
                    if overlap <= 0:
                        continue
                    role = str(roster["role"])
                    operational = float(roster["fte"]) * overlap
                    funded = (
                        line.fraction
                        * float(roster["fte_months"])
                        * overlap
                        / active
                    )
                    source_incremental[role] = (
                        source_incremental.get(role, 0.0) - funded
                    )
                    route_fte_months[role] = (
                        route_fte_months.get(role, 0.0) + operational
                    )
                base = base_fte_months_by_item.setdefault(line.item_id, {})
                for role, fte_months in route_fte_months.items():
                    base[role] = max(fte_months, base.get(role, 0.0))

            for role, fte_months in source_incremental.items():
                # Equivalent float expressions can leave a last-bit residual
                # after removing the roster component.
                if abs(fte_months) <= 1e-12:
                    continue
                incremental_fte_months[role] = (
                    incremental_fte_months.get(role, 0.0) + fte_months
                )
            if cost.org_base_item is None:
                continue
            base = base_fte_months_by_item.setdefault(cost.org_base_item, {})
            for role, fte in period["base_fte_by_role"].items():
                # Convert each source's period-average FTE back to FTE-months
                # before de-duplicating. This preserves one shared roster even
                # when selections emit final periods of different lengths.
                base[role] = max(
                    float(fte) * source_months,
                    base.get(role, 0.0),
                )

        incremental = {
            role: fte_months / combined_months if combined_months else 0.0
            for role, fte_months in sorted(incremental_fte_months.items())
        }
        base_fte_months: dict[str, float] = {}
        for item_id in sorted(base_fte_months_by_item):
            for role, fte_months in base_fte_months_by_item[item_id].items():
                base_fte_months[role] = (
                    base_fte_months.get(role, 0.0) + fte_months
                )
        base_fte = {
            role: fte_months / combined_months if combined_months else 0.0
            for role, fte_months in sorted(base_fte_months.items())
        }
        roles = sorted(set(incremental) | set(base_fte))
        periods.append(
            {
                "index": index,
                "label": f"Y{index + 1}",
                "start_month": index * 12,
                "months": combined_months,
                "cost": period_cost,
                "fte_by_role": incremental,
                "base_fte_by_role": base_fte,
                "total_fte_by_role": {
                    role: incremental.get(role, 0.0) + base_fte.get(role, 0.0)
                    for role in roles
                },
                "revenue": {"enabled": 0.0, "attributed": 0.0},
            }
        )
    return periods


def _stream_key(
    selection_id: str, stream: dict[str, Any], shared: bool
) -> tuple[Any, ...]:
    return (
        "" if shared else selection_id,
        stream["item_id"],
        stream["stream"],
        stream["family"],
        stream["unit"],
        stream["price_usd"],
        tuple(stream["volume_per_year"]),
        stream["starts"],
        stream["start_month"],
        stream["ramp_months"],
        stream["basis"],
        stream["assumed"],
    )


def _combine_revenue(
    selections: list[Any],
    costs: dict[str, SelectionCost],
    periods: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    menu_ids = {
        line.item
        for selection in selections
        for line in selection.selections
        if line.instance is None
    }
    funders = {selection.id: selection.funder for selection in selections}
    for selection in selections:
        cost = costs[selection.id]
        for stream in cost.revenue["by_stream"]:
            shared = stream["item_id"] in menu_ids
            key = _stream_key(selection.id, stream, shared)
            group = grouped.setdefault(
                key,
                {
                    key: stream[key]
                    for key in (
                        "item_id",
                        "stream",
                        "family",
                        "unit",
                        "price_usd",
                        "volume_per_year",
                        "starts",
                        "start_month",
                        "ramp_months",
                        "basis",
                        "assumed",
                    )
                }
                | {"shares": []},
            )
            group["shares"].append(
                {
                    "selection_id": selection.id,
                    "funder": funders[selection.id],
                    "enabled_usd": stream["enabled_usd"],
                    "attributed_usd": stream["attributed_usd"],
                    "by_period": [dict(row) for row in stream["by_period"]],
                }
            )

    streams: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda value: tuple(map(str, value))):
        group = grouped[key]
        shares = sorted(
            group.pop("shares"), key=lambda entry: entry["selection_id"]
        )
        by_period = []
        for index, period in enumerate(periods):
            share_rows = [
                share["by_period"][index]
                for share in shares
                if index < len(share["by_period"])
            ]
            by_period.append(
                {
                    "index": index,
                    "label": period["label"],
                    "enabled_usd": max(
                        (float(row["enabled_usd"]) for row in share_rows),
                        default=0.0,
                    ),
                    "attributed_usd": sum(
                        float(row["attributed_usd"]) for row in share_rows
                    ),
                }
            )
        streams.append(
            {
                **group,
                "shares": shares,
                "enabled_usd": sum(row["enabled_usd"] for row in by_period),
                "attributed_usd": sum(
                    row["attributed_usd"] for row in by_period
                ),
                "by_period": by_period,
            }
        )

    revenue_periods = []
    for index, period in enumerate(periods):
        revenue_periods.append(
            {
                "index": index,
                "label": period["label"],
                "start_month": period["start_month"],
                "months": period["months"],
                "enabled_usd": sum(
                    stream["by_period"][index]["enabled_usd"]
                    for stream in streams
                ),
                "attributed_usd": sum(
                    stream["by_period"][index]["attributed_usd"]
                    for stream in streams
                ),
            }
        )
    return {
        "by_stream": streams,
        "by_period": revenue_periods,
        "enabled_total": sum(
            period["enabled_usd"] for period in revenue_periods
        ),
        "attributed_total": sum(
            period["attributed_usd"] for period in revenue_periods
        ),
    }
