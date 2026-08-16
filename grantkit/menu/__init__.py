"""The budget model: menus, rates, selections, and their compiler.

Three documents — an org's priced work-item **menu**, a provider's
**rates** contract, and per-proposal **selections** over the menu — compile
deterministically into a budget. ``grantkit budget`` is the CLI entry;
:func:`run_gates` is the integrity linter (including the co-funding gate);
:func:`compile_selection` is the pure compile API.
:func:`compile_combined` builds a deterministic multi-selection scenario.

See ``docs/budget-model.md`` and ``docs/rates-contract.md``.
"""

from .combine import CombinedCost, compile_combined
from .engine import (
    ItemCost,
    SelectionCost,
    compile_selection,
    item_cost,
    selection_cost,
)
from .gates import run_combined_gates, run_gates
from .loader import Portfolio, PortfolioError, load_portfolio
from .model import model_bundle
from .resolve import (
    ResolvedItem,
    ResolvedRevenueStream,
    evaluate_form,
    resolve_item,
)
from .schema import (
    InlineInstance,
    Kind,
    KindPreset,
    Menu,
    MenuItem,
    NonPersonnelLine,
    OrgBase,
    Overheads,
    RateBenchmark,
    RateComponent,
    Rates,
    Resourcing,
    RoleRate,
    RosterLine,
    Selection,
    SelectionLine,
    UnitCost,
    as_number,
    validate_menu,
    validate_rates,
    validate_selection,
)

__all__ = [
    # Loader
    "load_portfolio",
    "Portfolio",
    "PortfolioError",
    "model_bundle",
    # Engine
    "compile_selection",
    "selection_cost",
    "item_cost",
    "ItemCost",
    "SelectionCost",
    "compile_combined",
    "CombinedCost",
    "resolve_item",
    "evaluate_form",
    "ResolvedItem",
    "ResolvedRevenueStream",
    # Gates
    "run_gates",
    "run_combined_gates",
    # Schemas
    "Menu",
    "MenuItem",
    "UnitCost",
    "Overheads",
    "Resourcing",
    "RosterLine",
    "NonPersonnelLine",
    "Kind",
    "KindPreset",
    "InlineInstance",
    "Rates",
    "RoleRate",
    "RateComponent",
    "RateBenchmark",
    "Selection",
    "SelectionLine",
    "OrgBase",
    "validate_menu",
    "validate_rates",
    "validate_selection",
    "as_number",
]
