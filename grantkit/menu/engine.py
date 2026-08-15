"""Pure budget-compilation arithmetic.

The compiled budget is a deterministic function of (menu, rates, selection):
the same inputs produce the same compiled values. All money is carried as
floats internally; rounding to whole dollars happens only at render time
(:mod:`grantkit.menu.render`).

Cost model (documented in ``docs/budget-model.md``)::

    item_cost(item, rates, unit_costs) -> ItemCost
      labor    = sum over roles of fte_months/12 x loaded_usd
      units    = sum over units of count x usd_per_unit
      contract = contract_usd
      flat     = amount_usd
      one_time = labor + units + contract + flat   (recurring excluded)
      recurring_usd_per_year carried separately

    selection_cost(selection, portfolio) -> SelectionCost
      per selected item with fraction f:
        work = f x one_time + f x recurring x window_months/12
      org_base = fraction x one_time(org_base.item)
                 (the window does NOT prorate flat blocks)
      overhead applies to every component EXCEPT amounts that came from a
      field covered by overhead_included: true (those already contain the
      fee, so the selection-level overhead must not re-apply)
      total = work + org_base + overhead
      fit  = total / target_usd, when a target is set

These functions assume referential integrity (run
:func:`grantkit.menu.gates.run_gates` first); an unresolved role, unit, or
item id raises ``KeyError``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .resolve import ResolvedItem, resolve_item
from .schema import Menu, MenuItem, Rates, Selection, SelectionLine, UnitCost

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .loader import Portfolio


@dataclass
class ItemCost:
    """The unweighted cost of one menu item."""

    item_id: str
    labor_usd: float = 0.0
    units_usd: float = 0.0
    contract_usd: float = 0.0
    flat_usd: float = 0.0
    recurring_usd_per_year: float = 0.0
    overhead_included: bool = False
    #: role -> {"fte_months": months, "usd": dollars}
    labor_by_role: dict[str, dict[str, float]] = field(default_factory=dict)
    #: Ordinary (non-roster) role labor, retained for incremental phasing.
    ordinary_labor_by_role: dict[str, dict[str, float]] = field(
        default_factory=dict, repr=False
    )
    #: Concrete roster lines with their active months and labor dollars.
    roster_lines: list[dict[str, Any]] = field(
        default_factory=list, repr=False
    )
    #: Direct contract dollars, excluding roster non-personnel run rate.
    direct_contract_usd: float = field(default=0.0, repr=False)
    #: Roster non-personnel dollars included in ``contract_usd``.
    non_personnel_usd: float = field(default=0.0, repr=False)

    @property
    def one_time_usd(self) -> float:
        """Labor + units + contract + flat (recurring excluded)."""
        return (
            self.labor_usd + self.units_usd + self.contract_usd + self.flat_usd
        )

    @property
    def overhead_bearing_one_time_usd(self) -> float:
        """The one-time portion the selection-level overhead applies to.

        With ``overhead_included: true`` the ``contract_usd`` /
        ``amount_usd`` dollars already contain org overheads. Roster labor
        follows the same rule because a roster-based org base is a single
        overhead-inclusive block; ordinary item labor and units continue to
        bear overhead under the v0 contract.
        """
        if self.overhead_included:
            ordinary_labor = sum(
                spend["usd"] for spend in self.ordinary_labor_by_role.values()
            )
            return ordinary_labor + self.units_usd
        return self.one_time_usd

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "labor_usd": self.labor_usd,
            "units_usd": self.units_usd,
            "contract_usd": self.contract_usd,
            "flat_usd": self.flat_usd,
            "one_time_usd": self.one_time_usd,
            "recurring_usd_per_year": self.recurring_usd_per_year,
            "overhead_included": self.overhead_included,
            "overhead_bearing_one_time_usd": (
                self.overhead_bearing_one_time_usd
            ),
            "labor_by_role": {
                role: dict(spend) for role, spend in self.labor_by_role.items()
            },
            "roster_by_role": _roster_by_role(self.roster_lines),
        }


@dataclass
class SelectedItemCost:
    """One selection line, costed and fraction-weighted."""

    item_id: str
    title: str
    type: str
    fraction: float
    item: ItemCost
    one_time_usd: float
    recurring_usd: float
    overhead_bearing_usd: float
    start_month: int = 0
    duration_months: float = 1.0
    outside_window_usd: float = 0.0
    resolved: Optional[ResolvedItem] = field(default=None, repr=False)

    @property
    def funded_usd(self) -> float:
        return self.one_time_usd + self.recurring_usd

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "type": self.type,
            "fraction": self.fraction,
            "item_one_time_usd": self.item.one_time_usd,
            "item_recurring_usd_per_year": (self.item.recurring_usd_per_year),
            "one_time_usd": self.one_time_usd,
            "recurring_usd": self.recurring_usd,
            "funded_usd": self.funded_usd,
            "start_month": self.start_month,
            "duration_months": self.duration_months,
            "overhead_bearing_usd": self.overhead_bearing_usd,
            "outside_window_usd": self.outside_window_usd,
        }


@dataclass
class SelectionCost:
    """The full compiled budget for one selection."""

    selection_id: str
    funder: str
    status: str
    window_months: int
    horizon_months: int
    currency: str
    target_usd: Optional[float]
    items: list[SelectedItemCost] = field(default_factory=list)
    #: role -> {"fte_months": ..., "loaded_usd": ..., "usd": ...}
    personnel: dict[str, dict[str, float]] = field(default_factory=dict)
    labor_usd: float = 0.0
    units_usd: float = 0.0
    contract_usd: float = 0.0
    flat_usd: float = 0.0
    recurring_usd: float = 0.0
    org_base_item: Optional[str] = None
    org_base_fraction: float = 0.0
    org_base_usd: float = 0.0
    overhead_rate: float = 0.0
    overhead_usd: float = 0.0
    total_usd: float = 0.0
    periods: list[dict[str, Any]] = field(default_factory=list)
    outside_window_usd: float = 0.0
    revenue: dict[str, Any] = field(
        default_factory=lambda: {
            "by_stream": [],
            "by_period": [],
            "enabled_total": 0.0,
            "attributed_total": 0.0,
        }
    )
    net_of_attributed_usd: float = 0.0
    estimates: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def work_usd(self) -> float:
        """Fraction-weighted work total (before org base and overhead)."""
        return sum(line.funded_usd for line in self.items)

    @property
    def fit(self) -> Optional[float]:
        if self.target_usd:
            return self.total_usd / self.target_usd
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "funder": self.funder,
            "status": self.status,
            "window_months": self.window_months,
            "horizon_months": self.horizon_months,
            "currency": self.currency,
            "target_usd": self.target_usd,
            "items": [line.to_dict() for line in self.items],
            "personnel": {
                role: dict(spend) for role, spend in self.personnel.items()
            },
            "categories": {
                "labor_usd": self.labor_usd,
                "units_usd": self.units_usd,
                "contract_usd": self.contract_usd,
                "flat_usd": self.flat_usd,
                "recurring_usd": self.recurring_usd,
                "org_base_usd": self.org_base_usd,
                "overhead_usd": self.overhead_usd,
            },
            "org_base": (
                {
                    "item": self.org_base_item,
                    "fraction": self.org_base_fraction,
                    "usd": self.org_base_usd,
                }
                if self.org_base_item
                else None
            ),
            "overhead_rate": self.overhead_rate,
            "work_usd": self.work_usd,
            "total_usd": self.total_usd,
            "fit": self.fit,
            "periods": self.periods,
            "outside_window_usd": self.outside_window_usd,
            "revenue": self.revenue,
            "net_of_attributed_usd": self.net_of_attributed_usd,
            "estimates": {
                path: dict(self.estimates[path])
                for path in sorted(self.estimates)
            },
        }


def _roster_by_role(
    roster_lines: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Aggregate concrete roster lines for structured output."""
    result: dict[str, dict[str, float]] = {}
    for line in roster_lines:
        role = str(line["role"])
        entry = result.setdefault(
            role, {"fte": 0.0, "months": 0.0, "usd": 0.0}
        )
        entry["fte"] += float(line["fte"])
        entry["months"] += float(line["fte_months"])
        entry["usd"] += float(line["usd"])
    return result


def item_cost(
    item: MenuItem | ResolvedItem,
    rates: Rates,
    unit_costs: dict[str, UnitCost],
) -> ItemCost:
    """Cost one menu item against the rates and unit prices.

    Raises:
        KeyError: on a role or unit name that does not resolve.
    """
    roles = rates.roles_by_name
    labor_by_role: dict[str, dict[str, float]] = {}
    ordinary_labor_by_role: dict[str, dict[str, float]] = {}
    labor = 0.0
    for role, months in item.resourcing.fte_months.items():
        if role not in roles:
            raise KeyError(
                f"Item '{item.id}' references unknown role '{role}'"
            )
        usd = months / 12.0 * roles[role].loaded_usd
        labor_by_role[role] = {"fte_months": months, "usd": usd}
        ordinary_labor_by_role[role] = {
            "fte_months": months,
            "usd": usd,
        }
        labor += usd
    duration = float(item.duration_months or 1.0)
    roster_lines: list[dict[str, Any]] = []
    for roster in item.resourcing.roster:
        role = roster.role
        if role not in roles:
            raise KeyError(
                f"Item '{item.id}' roster references unknown role '{role}'"
            )
        active_months = (
            float(roster.months) if roster.months is not None else duration
        )
        fte_months = float(roster.fte) * active_months
        usd = fte_months / 12.0 * roles[role].loaded_usd
        roster_lines.append(
            {
                "role": role,
                "fte": float(roster.fte),
                "months": active_months,
                "fte_months": fte_months,
                "usd": usd,
            }
        )
        entry = labor_by_role.setdefault(role, {"fte_months": 0.0, "usd": 0.0})
        entry["fte_months"] += fte_months
        entry["usd"] += usd
        labor += usd
    units = 0.0
    for unit, count in item.resourcing.units.items():
        if unit not in unit_costs:
            raise KeyError(
                f"Item '{item.id}' references unknown unit '{unit}'"
            )
        units += count * unit_costs[unit].usd_per_unit
    direct_contract = item.resourcing.contract_usd or 0.0
    non_personnel = (
        (item.resourcing.non_personnel_usd_per_year or 0.0) * duration / 12.0
    )
    return ItemCost(
        item_id=item.id,
        labor_usd=labor,
        units_usd=units,
        contract_usd=direct_contract + non_personnel,
        flat_usd=item.resourcing.amount_usd or 0.0,
        recurring_usd_per_year=(item.resourcing.recurring_usd_per_year or 0.0),
        overhead_included=item.resourcing.overhead_included,
        labor_by_role=labor_by_role,
        ordinary_labor_by_role=ordinary_labor_by_role,
        roster_lines=roster_lines,
        direct_contract_usd=direct_contract,
        non_personnel_usd=non_personnel,
    )


@dataclass
class _LineContext:
    line: SelectionLine
    resolved: ResolvedItem
    costed: ItemCost
    selected: SelectedItemCost


def _merge_estimates(
    target: dict[str, dict[str, Any]],
    source: dict[str, dict[str, Any]],
) -> None:
    for path, metadata in source.items():
        target.setdefault(path, dict(metadata))


def _estimate_metadata(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, dict) or "central" not in value:
        return None
    return {
        key: value[key]
        for key in ("central", "low", "high", "basis", "source")
        if key in value
    }


def _collect_raw_estimates(
    target: dict[str, dict[str, Any]], value: Any, path: str
) -> None:
    """Collect estimate objects below one used raw model fragment."""
    metadata = _estimate_metadata(value)
    if metadata is not None:
        target.setdefault(path, metadata)
        return
    if isinstance(value, dict):
        for key, entry in value.items():
            _collect_raw_estimates(target, entry, f"{path}.{key}")
    elif isinstance(value, list):
        for index, entry in enumerate(value):
            _collect_raw_estimates(target, entry, f"{path}.{index}")


def _collect_cost_estimates(
    cost: SelectionCost,
    resolved: ResolvedItem,
    costed: ItemCost,
    menu: Menu,
    rates: Rates,
) -> None:
    _merge_estimates(cost.estimates, resolved.estimates)
    for unit in resolved.resourcing.units:
        unit_cost = menu.unit_costs.get(unit)
        if unit_cost is None:
            continue
        _collect_raw_estimates(
            cost.estimates,
            unit_cost.raw.get("usd_per_unit"),
            f"menu.unit_costs.{unit}.usd_per_unit",
        )
    for role in costed.labor_by_role:
        rate = rates.roles_by_name.get(role)
        if rate is not None:
            _collect_raw_estimates(
                cost.estimates,
                rate.raw,
                f"rates.roles.{role}",
            )


def selection_cost(
    selection: Selection, portfolio: "Portfolio"
) -> SelectionCost:
    """Compile one selection against its portfolio's menu and rates.

    Raises:
        KeyError: on an item, role, or unit id that does not resolve.
    """
    menu: Menu = portfolio.menu
    rates: Rates = portfolio.rates
    items_by_id = menu.items_by_id
    window = selection.window_months
    rate = menu.overheads.fiscal_sponsorship_rate

    cost = SelectionCost(
        selection_id=selection.id,
        funder=selection.funder,
        status=selection.status,
        window_months=window,
        horizon_months=selection.horizon_months or window,
        currency=menu.currency,
        target_usd=selection.target_usd,
        overhead_rate=rate,
    )

    overhead_base = 0.0
    contexts: list[_LineContext] = []
    for line in selection.selections:
        if line.instance is not None:
            resolved = resolve_item(
                line.instance,
                menu.kinds,
                path=(
                    f"selection.{selection.id}.instances."
                    f"{line.instance.id}"
                ),
            )
        else:
            if line.item not in items_by_id:
                raise KeyError(
                    f"Selection '{selection.id}' references unknown item "
                    f"'{line.item}'"
                )
            item = items_by_id[line.item]
            resolved = resolve_item(
                item, menu.kinds, path=f"menu.items.{item.id}"
            )
        costed = item_cost(resolved, rates, menu.unit_costs)
        f = line.fraction
        one_time = f * costed.one_time_usd
        recurring = costed.recurring_usd_per_year * (f * window / 12.0)
        bearing = f * costed.overhead_bearing_one_time_usd + recurring
        selected = SelectedItemCost(
            item_id=resolved.id,
            title=resolved.title,
            type=resolved.type,
            fraction=f,
            item=costed,
            one_time_usd=one_time,
            recurring_usd=recurring,
            overhead_bearing_usd=bearing,
            start_month=line.start_month,
            duration_months=resolved.duration_months,
            resolved=resolved,
        )
        cost.items.append(selected)
        contexts.append(_LineContext(line, resolved, costed, selected))
        _collect_cost_estimates(cost, resolved, costed, menu, rates)
        cost.labor_usd += f * costed.labor_usd
        cost.units_usd += f * costed.units_usd
        cost.contract_usd += f * costed.contract_usd
        cost.flat_usd += f * costed.flat_usd
        cost.recurring_usd += recurring
        overhead_base += bearing
        # Explicit-zero lines are declarations; they stay in the item
        # list but add no personnel rows.
        if f > 0:
            for role, spend in costed.labor_by_role.items():
                entry = cost.personnel.setdefault(
                    role,
                    {
                        "fte_months": 0.0,
                        "loaded_usd": rates.roles_by_name[role].loaded_usd,
                        "usd": 0.0,
                    },
                )
                entry["fte_months"] += f * spend["fte_months"]
                entry["usd"] += f * spend["usd"]

    base_context: Optional[tuple[ResolvedItem, ItemCost]] = None
    if selection.org_base is not None:
        base_id = selection.org_base.item
        if base_id not in items_by_id:
            raise KeyError(
                f"Selection '{selection.id}' org_base references unknown "
                f"item '{base_id}'"
            )
        base_item = items_by_id[base_id]
        resolved_base = resolve_item(
            base_item, menu.kinds, path=f"menu.items.{base_id}"
        )
        base_cost = item_cost(resolved_base, rates, menu.unit_costs)
        base_context = (resolved_base, base_cost)
        _collect_cost_estimates(cost, resolved_base, base_cost, menu, rates)
        base_fraction = selection.org_base.fraction
        cost.org_base_item = base_id
        cost.org_base_fraction = base_fraction
        cost.org_base_usd = base_fraction * base_cost.one_time_usd
        overhead_base += (
            base_fraction * base_cost.overhead_bearing_one_time_usd
        )
        if base_fraction > 0:
            for role, spend in base_cost.labor_by_role.items():
                entry = cost.personnel.setdefault(
                    role,
                    {
                        "fte_months": 0.0,
                        "loaded_usd": rates.roles_by_name[role].loaded_usd,
                        "usd": 0.0,
                    },
                )
                entry["fte_months"] += base_fraction * spend["fte_months"]
                entry["usd"] += base_fraction * spend["usd"]

    cost.overhead_usd = rate * overhead_base
    cost.total_usd = cost.work_usd + cost.org_base_usd + cost.overhead_usd
    _build_periods(cost, selection, contexts, base_context, rates)
    _build_revenue(cost, contexts)
    cost.net_of_attributed_usd = (
        cost.total_usd - cost.revenue["attributed_total"]
    )
    return cost


_PERIOD_CATEGORIES = (
    "labor",
    "units",
    "contract",
    "flat",
    "recurring",
    "org_base",
    "overhead",
)


def _overlap(
    start_a: float, end_a: float, start_b: float, end_b: float
) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _display_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _period_extent(
    cost: SelectionCost,
    contexts: list[_LineContext],
    base_context: Optional[tuple[ResolvedItem, ItemCost]],
) -> float:
    extent = float(max(cost.window_months, cost.horizon_months))
    for context in contexts:
        if context.line.fraction == 0 or context.costed.one_time_usd == 0:
            continue
        active = context.resolved.duration_months
        if context.costed.roster_lines:
            active = max(
                active,
                *(
                    float(line["months"])
                    for line in context.costed.roster_lines
                ),
            )
        extent = max(extent, float(context.line.start_month) + active)
    if base_context is not None and cost.org_base_fraction != 0:
        resolved, costed = base_context
        if costed.roster_lines or costed.non_personnel_usd:
            active = resolved.duration_months
            if costed.roster_lines:
                active = max(
                    active,
                    *(float(line["months"]) for line in costed.roster_lines),
                )
            extent = max(extent, active)
    return extent


def _empty_periods(extent: float) -> list[dict[str, Any]]:
    count = max(1, math.ceil(extent / 12.0))
    periods: list[dict[str, Any]] = []
    for index in range(count):
        start = float(index * 12)
        end = min(float((index + 1) * 12), extent)
        months = max(0.0, end - start)
        periods.append(
            {
                "index": index,
                "label": f"Y{index + 1}",
                "start_month": _display_number(start),
                "months": _display_number(months),
                "cost": {key: 0.0 for key in _PERIOD_CATEGORIES},
                "fte_by_role": {},
                "base_fte_by_role": {},
                "revenue": {"enabled": 0.0, "attributed": 0.0},
                "_bearing": 0.0,
            }
        )
    return periods


def _phase_source(
    periods: list[dict[str, Any]],
    category: str,
    amount: float,
    bearing_amount: float,
    start: float,
    end: float,
) -> None:
    duration = end - start
    if duration <= 0:
        return
    for period in periods:
        period_start = float(period["start_month"])
        period_end = period_start + float(period["months"])
        share = _overlap(start, end, period_start, period_end) / duration
        if share:
            period["cost"][category] += amount * share
            period["_bearing"] += bearing_amount * share


def _outside_source(
    amount: float,
    bearing_amount: float,
    start: float,
    end: float,
    window: float,
    overhead_rate: float,
) -> float:
    duration = end - start
    if duration <= 0:
        return 0.0
    outside_share = 1.0 - _overlap(start, end, 0.0, window) / duration
    return (
        amount * outside_share + overhead_rate * bearing_amount * outside_share
    )


def _phase_incremental_fte(
    periods: list[dict[str, Any]],
    role: str,
    fte_months: float,
    start: float,
    end: float,
) -> None:
    duration = end - start
    if duration <= 0 or fte_months == 0:
        return
    for period in periods:
        period_start = float(period["start_month"])
        months = float(period["months"])
        period_end = period_start + months
        overlap = _overlap(start, end, period_start, period_end)
        if overlap and months:
            period["fte_by_role"][role] = (
                period["fte_by_role"].get(role, 0.0)
                + fte_months * overlap / duration / months
            )


def _phase_base_fte(
    periods: list[dict[str, Any]],
    role: str,
    fte: float,
    months_active: float,
) -> None:
    if months_active <= 0 or fte == 0:
        return
    for period in periods:
        period_start = float(period["start_month"])
        months = float(period["months"])
        period_end = period_start + months
        overlap = _overlap(0.0, months_active, period_start, period_end)
        if overlap and months:
            period["base_fte_by_role"][role] = (
                period["base_fte_by_role"].get(role, 0.0)
                + fte * overlap / months
            )


def _build_periods(
    cost: SelectionCost,
    selection: Selection,
    contexts: list[_LineContext],
    base_context: Optional[tuple[ResolvedItem, ItemCost]],
    rates: Rates,
) -> None:
    """Build conserved cost periods and staffing after legacy arithmetic."""
    del rates  # rates are already reflected in each ItemCost.
    extent = _period_extent(cost, contexts, base_context)
    periods = _empty_periods(extent)
    window = float(cost.window_months)
    rate = cost.overhead_rate
    outside_total = 0.0

    for context in contexts:
        selected = context.selected
        costed = context.costed
        f = context.line.fraction
        start = float(context.line.start_month)
        end = start + context.resolved.duration_months
        outside = 0.0

        ordinary_labor = sum(
            spend["usd"] for spend in costed.ordinary_labor_by_role.values()
        )
        amount = f * ordinary_labor
        _phase_source(periods, "labor", amount, amount, start, end)
        outside += _outside_source(amount, amount, start, end, window, rate)
        for role, spend in costed.ordinary_labor_by_role.items():
            _phase_incremental_fte(
                periods,
                role,
                f * spend["fte_months"],
                start,
                end,
            )

        for roster in costed.roster_lines:
            roster_end = start + float(roster["months"])
            amount = f * float(roster["usd"])
            bearing = 0.0 if costed.overhead_included else amount
            _phase_source(periods, "labor", amount, bearing, start, roster_end)
            outside += _outside_source(
                amount, bearing, start, roster_end, window, rate
            )
            _phase_incremental_fte(
                periods,
                str(roster["role"]),
                f * float(roster["fte_months"]),
                start,
                roster_end,
            )

        amount = f * costed.units_usd
        _phase_source(periods, "units", amount, amount, start, end)
        outside += _outside_source(amount, amount, start, end, window, rate)

        amount = f * costed.direct_contract_usd
        bearing = 0.0 if costed.overhead_included else amount
        _phase_source(periods, "contract", amount, bearing, start, end)
        outside += _outside_source(amount, bearing, start, end, window, rate)

        amount = f * costed.non_personnel_usd
        bearing = 0.0 if costed.overhead_included else amount
        _phase_source(periods, "contract", amount, bearing, start, end)
        outside += _outside_source(amount, bearing, start, end, window, rate)

        amount = f * costed.flat_usd
        bearing = 0.0 if costed.overhead_included else amount
        _phase_source(periods, "flat", amount, bearing, start, end)
        outside += _outside_source(amount, bearing, start, end, window, rate)

        _phase_source(
            periods,
            "recurring",
            selected.recurring_usd,
            selected.recurring_usd,
            0.0,
            window,
        )
        selected.outside_window_usd = outside
        outside_total += outside

    if base_context is not None and cost.org_base_fraction != 0:
        resolved, costed = base_context
        fraction = cost.org_base_fraction
        roster_labor = sum(float(line["usd"]) for line in costed.roster_lines)
        remainder = (
            costed.one_time_usd - roster_labor - costed.non_personnel_usd
        )
        roster_bearing = 0.0 if costed.overhead_included else roster_labor
        non_personnel_bearing = (
            0.0 if costed.overhead_included else costed.non_personnel_usd
        )
        remainder_bearing = (
            costed.overhead_bearing_one_time_usd
            - roster_bearing
            - non_personnel_bearing
        )
        _phase_source(
            periods,
            "org_base",
            fraction * remainder,
            fraction * remainder_bearing,
            0.0,
            window,
        )
        for roster in costed.roster_lines:
            active = float(roster["months"])
            amount = fraction * float(roster["usd"])
            bearing = 0.0 if costed.overhead_included else amount
            _phase_source(periods, "org_base", amount, bearing, 0.0, active)
            outside_total += _outside_source(
                amount, bearing, 0.0, active, window, rate
            )
            _phase_base_fte(
                periods,
                str(roster["role"]),
                float(roster["fte"]),
                active,
            )
        if costed.non_personnel_usd:
            active = resolved.duration_months
            amount = fraction * costed.non_personnel_usd
            bearing = 0.0 if costed.overhead_included else amount
            _phase_source(periods, "org_base", amount, bearing, 0.0, active)
            outside_total += _outside_source(
                amount, bearing, 0.0, active, window, rate
            )
        for role, spend in costed.ordinary_labor_by_role.items():
            _phase_incremental_fte(
                periods,
                role,
                fraction * spend["fte_months"],
                0.0,
                window,
            )

    for period in periods:
        period["cost"]["overhead"] = rate * float(period.pop("_bearing"))

    targets = {
        "labor": cost.labor_usd,
        "units": cost.units_usd,
        "contract": cost.contract_usd,
        "flat": cost.flat_usd,
        "recurring": cost.recurring_usd,
        "org_base": cost.org_base_usd,
        "overhead": cost.overhead_usd,
    }
    # Float-only phasing can leave last-bit residuals. Reconcile those into
    # the final bucket without changing any legacy category or total.
    for category, target in targets.items():
        allocated = sum(float(period["cost"][category]) for period in periods)
        periods[-1]["cost"][category] += target - allocated
    for period in periods:
        period["cost"]["total"] = sum(
            float(period["cost"][category])
            for category in _PERIOD_CATEGORIES
            if category != "total"
        )

    cost.periods = periods
    cost.outside_window_usd = outside_total


def _ramp_primitive(elapsed: float, ramp_months: float) -> float:
    if ramp_months <= 0:
        return elapsed
    if elapsed <= ramp_months:
        return elapsed * elapsed / (2.0 * ramp_months)
    return elapsed - ramp_months / 2.0


def _stream_revenue_in_period(
    stream: Any,
    stream_start: float,
    period_start: float,
    period_end: float,
    horizon: float,
) -> float:
    end = min(period_end, horizon)
    if end <= max(period_start, stream_start) or not stream.volume_per_year:
        return 0.0
    ramp = float(stream.ramp_months or 0.0)
    years = max(0, math.ceil((horizon - stream_start) / 12.0))
    total = 0.0
    for year in range(years):
        year_start = stream_start + 12.0 * year
        year_end = year_start + 12.0
        start = max(period_start, stream_start, year_start)
        stop = min(end, year_end)
        if stop <= start:
            continue
        volume = stream.volume_per_year[
            min(year, len(stream.volume_per_year) - 1)
        ]
        elapsed_start = start - stream_start
        elapsed_end = stop - stream_start
        ramp_area = _ramp_primitive(elapsed_end, ramp) - _ramp_primitive(
            elapsed_start, ramp
        )
        total += stream.price_usd * volume / 12.0 * ramp_area
    return total


def _stream_basis(stream: Any) -> tuple[Optional[str], bool]:
    bases = [
        metadata.get("basis")
        for metadata in stream.estimates.values()
        if metadata.get("basis") is not None
    ]
    basis = str(bases[0]) if bases else None
    return basis, any(value == "assumed" for value in bases)


def _build_revenue(cost: SelectionCost, contexts: list[_LineContext]) -> None:
    periods = cost.periods
    horizon = float(cost.horizon_months)
    by_stream: list[dict[str, Any]] = []
    enabled_by_period = [0.0 for _ in periods]
    attributed_by_period = [0.0 for _ in periods]

    for context in contexts:
        fraction = context.line.fraction
        for stream in context.resolved.revenue:
            stream_start = float(context.line.start_month)
            if stream.starts == "completion":
                stream_start += context.resolved.duration_months
            enabled_periods: list[float] = []
            attributed_periods: list[float] = []
            for index, period in enumerate(periods):
                period_start = float(period["start_month"])
                period_end = period_start + float(period["months"])
                enabled = (
                    _stream_revenue_in_period(
                        stream,
                        stream_start,
                        period_start,
                        period_end,
                        horizon,
                    )
                    if fraction > 0
                    else 0.0
                )
                attributed = enabled * fraction
                enabled_periods.append(enabled)
                attributed_periods.append(attributed)
                enabled_by_period[index] += enabled
                attributed_by_period[index] += attributed
            basis, assumed = _stream_basis(stream)
            by_stream.append(
                {
                    "item_id": context.resolved.id,
                    "stream": stream.stream,
                    "family": stream.family,
                    "unit": stream.unit,
                    "price_usd": stream.price_usd,
                    "volume_per_year": list(stream.volume_per_year),
                    "starts": stream.starts,
                    "start_month": stream_start,
                    "ramp_months": float(stream.ramp_months or 0.0),
                    "basis": basis,
                    "assumed": assumed,
                    "enabled_usd": sum(enabled_periods),
                    "attributed_usd": sum(attributed_periods),
                    "by_period": [
                        {
                            "index": period["index"],
                            "label": period["label"],
                            "enabled_usd": enabled_periods[index],
                            "attributed_usd": attributed_periods[index],
                        }
                        for index, period in enumerate(periods)
                    ],
                }
            )

    revenue_periods = []
    for index, period in enumerate(periods):
        enabled = enabled_by_period[index]
        attributed = attributed_by_period[index]
        period["revenue"] = {
            "enabled": enabled,
            "attributed": attributed,
        }
        revenue_periods.append(
            {
                "index": period["index"],
                "label": period["label"],
                "start_month": period["start_month"],
                "months": period["months"],
                "enabled_usd": enabled,
                "attributed_usd": attributed,
            }
        )
    cost.revenue = {
        "by_stream": by_stream,
        "by_period": revenue_periods,
        "enabled_total": sum(enabled_by_period),
        "attributed_total": sum(attributed_by_period),
    }


#: Public alias — the package-level compile API.
compile_selection = selection_cost
