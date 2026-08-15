"""Pure budget-compilation arithmetic.

The compiled budget is a deterministic function of (menu, rates, selection):
same inputs produce the same output, byte for byte. All money is carried as
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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .schema import Menu, MenuItem, Rates, Selection, UnitCost

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
        ``amount_usd`` dollars already contain org overheads, so only
        labor and units remain overhead-bearing.
        """
        if self.overhead_included:
            return self.labor_usd + self.units_usd
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
            "labor_by_role": {
                role: dict(spend) for role, spend in self.labor_by_role.items()
            },
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
        }


@dataclass
class SelectionCost:
    """The full compiled budget for one selection."""

    selection_id: str
    funder: str
    status: str
    window_months: int
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
            "total_usd": self.total_usd,
            "fit": self.fit,
        }


def item_cost(
    item: MenuItem, rates: Rates, unit_costs: dict[str, UnitCost]
) -> ItemCost:
    """Cost one menu item against the rates and unit prices.

    Raises:
        KeyError: on a role or unit name that does not resolve.
    """
    roles = rates.roles_by_name
    labor_by_role: dict[str, dict[str, float]] = {}
    labor = 0.0
    for role, months in item.resourcing.fte_months.items():
        if role not in roles:
            raise KeyError(
                f"Item '{item.id}' references unknown role '{role}'"
            )
        usd = months / 12.0 * roles[role].loaded_usd
        labor_by_role[role] = {"fte_months": months, "usd": usd}
        labor += usd
    units = 0.0
    for unit, count in item.resourcing.units.items():
        if unit not in unit_costs:
            raise KeyError(
                f"Item '{item.id}' references unknown unit '{unit}'"
            )
        units += count * unit_costs[unit].usd_per_unit
    return ItemCost(
        item_id=item.id,
        labor_usd=labor,
        units_usd=units,
        contract_usd=item.resourcing.contract_usd or 0.0,
        flat_usd=item.resourcing.amount_usd or 0.0,
        recurring_usd_per_year=(item.resourcing.recurring_usd_per_year or 0.0),
        overhead_included=item.resourcing.overhead_included,
        labor_by_role=labor_by_role,
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
        currency=menu.currency,
        target_usd=selection.target_usd,
        overhead_rate=rate,
    )

    overhead_base = 0.0
    for line in selection.selections:
        if line.item not in items_by_id:
            raise KeyError(
                f"Selection '{selection.id}' references unknown item "
                f"'{line.item}'"
            )
        item = items_by_id[line.item]
        costed = item_cost(item, rates, menu.unit_costs)
        f = line.fraction
        one_time = f * costed.one_time_usd
        recurring = f * costed.recurring_usd_per_year * window / 12.0
        bearing = f * costed.overhead_bearing_one_time_usd + recurring
        cost.items.append(
            SelectedItemCost(
                item_id=item.id,
                title=item.title,
                type=item.type,
                fraction=f,
                item=costed,
                one_time_usd=one_time,
                recurring_usd=recurring,
                overhead_bearing_usd=bearing,
            )
        )
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

    if selection.org_base is not None:
        base_id = selection.org_base.item
        if base_id not in items_by_id:
            raise KeyError(
                f"Selection '{selection.id}' org_base references unknown "
                f"item '{base_id}'"
            )
        base_item = items_by_id[base_id]
        base_cost = item_cost(base_item, rates, menu.unit_costs)
        base_fraction = selection.org_base.fraction
        cost.org_base_item = base_id
        cost.org_base_fraction = base_fraction
        cost.org_base_usd = base_fraction * base_cost.one_time_usd
        overhead_base += (
            base_fraction * base_cost.overhead_bearing_one_time_usd
        )

    cost.overhead_usd = rate * overhead_base
    cost.total_usd = cost.work_usd + cost.org_base_usd + cost.overhead_usd
    return cost


#: Public alias — the package-level compile API.
compile_selection = selection_cost
