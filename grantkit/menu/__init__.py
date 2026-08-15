"""The budget model: menus, rates, selections, and their compiler.

Three documents — an org's priced work-item **menu**, a provider's
**rates** contract, and per-proposal **selections** over the menu — compile
deterministically into a budget. ``grantkit budget`` is the CLI entry;
:func:`run_gates` is the integrity linter (including the co-funding gate);
:func:`compile_selection` is the pure compile API.

See ``docs/budget-model.md`` and ``docs/rates-contract.md``.
"""

from .engine import (
    ItemCost,
    SelectionCost,
    compile_selection,
    item_cost,
    selection_cost,
)
from .gates import run_gates
from .loader import Portfolio, PortfolioError, load_portfolio
from .schema import (
    Menu,
    MenuItem,
    OrgBase,
    Overheads,
    RateBenchmark,
    RateComponent,
    Rates,
    Resourcing,
    RoleRate,
    Selection,
    SelectionLine,
    UnitCost,
    validate_menu,
    validate_rates,
    validate_selection,
)

__all__ = [
    # Loader
    "load_portfolio",
    "Portfolio",
    "PortfolioError",
    # Engine
    "compile_selection",
    "selection_cost",
    "item_cost",
    "ItemCost",
    "SelectionCost",
    # Gates
    "run_gates",
    # Schemas
    "Menu",
    "MenuItem",
    "UnitCost",
    "Overheads",
    "Resourcing",
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
]
