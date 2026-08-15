"""Integrity gates over a portfolio (menu + rates + selections).

:func:`run_gates` returns a flat list of :class:`CheckItem` findings, the
same structure every other GrantKit check produces. Errors are structural or
integrity violations; warnings are advisory heuristics, documented as such —
they are GrantKit's own sanity checks, never invented funder rules.

Gate order:

1. Schema validation of all three document kinds (``menu_invalid`` /
   ``rates_invalid`` / ``selection_invalid``), plus cross-document basics
   (currency mismatch, duplicate selection ids). Schema errors
   short-circuit: structural gates need well-formed documents.
2. Menu/rates integrity: unknown roles and units, unresolved dependencies,
   dependency cycles, and the advisory rates heuristics.
3. Portfolio fraction ranges and the co-funding gate
   (``cofunding_over_allocated``): for each item, the
   summed fractions across ``live``/``awarded`` selections must not exceed
   1 (tolerance 1e-9). Drafts are free to over-plan — the invariant binds
   simultaneous live applications, and fires when they go live.
4. Per-selection gates: unknown items, duplicates,
   org-base typing, unfunded dependencies, the advisory target check, and
   funder caps from a rule pack when one is bound.

For a selection's ``CheckItem``s the ``section`` field carries the
selection id, so table output shows which proposal each finding belongs to.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Optional

from ..core.checks import CheckItem
from ..packs import FunderPack
from .engine import selection_cost
from .loader import Portfolio
from .money import format_money, format_percent, round_half_up
from .schema import (
    Selection,
    validate_menu,
    validate_rates,
    validate_selection,
)

#: Co-funding tolerance: fractions may sum to exactly 1, and float noise
#: below this bound is not an over-allocation.
COFUNDING_TOLERANCE = 1e-9

#: Selection statuses the co-funding invariant binds.
BINDING_STATUSES = {"live", "awarded"}

#: Advisory load-factor band; outside it the rate looks suspicious.
LOAD_FACTOR_MIN = 1.05
LOAD_FACTOR_MAX = 2.0

#: Components must sum to loaded within this many dollars.
COMPONENTS_TOLERANCE_USD = 1.0


def _contains_non_finite_float(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(
            _contains_non_finite_float(entry) for entry in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite_float(entry) for entry in value)
    return False


def _non_finite_finding(selection_id: str) -> CheckItem:
    return CheckItem(
        level="error",
        rule="budget_non_finite",
        message=(
            f"Selection '{selection_id}' produces arithmetic outside the "
            "finite numeric range; reduce the input magnitudes."
        ),
        section=selection_id,
    )


def run_gates(
    portfolio: Portfolio,
    selection_id: Optional[str] = None,
    pack: Optional[FunderPack] = None,
) -> list[CheckItem]:
    """Run every integrity gate over ``portfolio``.

    With ``selection_id``, per-selection gates run for that selection only
    (portfolio-wide gates — schema, menu/rates integrity, co-funding —
    always run). With ``pack``, the pack's ``budget_rules`` caps are
    applied to each compiled selection.
    """
    items = _schema_gates(portfolio)
    if any(item.level == "error" for item in items):
        return items

    items += _menu_gates(portfolio)
    items += _rates_gates(portfolio)
    items += _fraction_gates(portfolio)
    items += _cofunding_gate(portfolio)

    if selection_id is not None:
        target = portfolio.get_selection(selection_id)
        if target is None:
            available = ", ".join(portfolio.selection_ids) or "(none)"
            items.append(
                CheckItem(
                    level="error",
                    rule="unknown_selection",
                    message=(
                        f"Selection '{selection_id}' was not found in the "
                        f"portfolio (available: {available})."
                    ),
                )
            )
            return items
        scope = [target]
    else:
        scope = list(portfolio.selections)
    for selection in scope:
        items += _selection_gates(portfolio, selection, pack)
    return items


# -- 1. schema ----------------------------------------------------------


def _schema_gates(portfolio: Portfolio) -> list[CheckItem]:
    out: list[CheckItem] = []
    for message in validate_menu(portfolio.menu_data):
        out.append(
            CheckItem(
                level="error",
                rule="menu_invalid",
                message=f"menu.yaml: {message}",
            )
        )
    for message in validate_rates(portfolio.rates_data):
        out.append(
            CheckItem(
                level="error",
                rule="rates_invalid",
                message=f"rates.yaml: {message}",
            )
        )
    seen_ids: set[str] = set()
    for data, selection in zip(
        portfolio.selections_data, portfolio.selections
    ):
        sid = selection.id or "(unnamed)"
        for message in validate_selection(data):
            out.append(
                CheckItem(
                    level="error",
                    rule="selection_invalid",
                    message=f"selection '{sid}': {message}",
                    section=selection.id or None,
                )
            )
        if selection.id in seen_ids:
            out.append(
                CheckItem(
                    level="error",
                    rule="selection_invalid",
                    message=(
                        f"duplicate selection id '{selection.id}' — ids "
                        f"must be unique across the portfolio"
                    ),
                    section=selection.id,
                )
            )
        elif selection.id:
            seen_ids.add(selection.id)
    menu_currency = portfolio.menu_data.get("currency")
    rates_currency = portfolio.rates_data.get("currency")
    if (
        isinstance(menu_currency, str)
        and isinstance(rates_currency, str)
        and menu_currency != rates_currency
    ):
        out.append(
            CheckItem(
                level="error",
                rule="rates_invalid",
                message=(
                    f"rates.yaml currency '{rates_currency}' does not "
                    f"match menu.yaml currency '{menu_currency}' "
                    f"(single-currency portfolios only)"
                ),
            )
        )
    return out


# -- 2. menu / rates integrity ------------------------------------------


def _menu_gates(portfolio: Portfolio) -> list[CheckItem]:
    out: list[CheckItem] = []
    menu = portfolio.menu
    known_roles = set(portfolio.rates.roles_by_name)
    known_items = set(menu.items_by_id)
    provider = portfolio.rates.provider or "rates.yaml"

    for item in menu.items:
        for role in item.resourcing.fte_months:
            if role not in known_roles:
                out.append(
                    CheckItem(
                        level="error",
                        rule="unknown_role",
                        message=(
                            f"Item '{item.id}' resourcing references "
                            f"role '{role}', which is not present in "
                            f"the rates ({provider})."
                        ),
                    )
                )
        for unit in item.resourcing.units:
            if unit not in menu.unit_costs:
                out.append(
                    CheckItem(
                        level="error",
                        rule="unknown_unit",
                        message=(
                            f"Item '{item.id}' references unit "
                            f"'{unit}', which is not present in the "
                            f"menu unit_costs."
                        ),
                    )
                )
        for dep in item.dependencies:
            if dep not in known_items:
                out.append(
                    CheckItem(
                        level="error",
                        rule="dependency_unresolved",
                        message=(
                            f"Item '{item.id}' depends on unknown "
                            f"item '{dep}'."
                        ),
                    )
                )
    out += _cycle_gate(portfolio)
    return out


def _cycle_gate(portfolio: Portfolio) -> list[CheckItem]:
    """Detect dependency cycles with an iterative DFS in menu order."""
    menu = portfolio.menu
    known = menu.items_by_id
    out: list[CheckItem] = []
    done: set[str] = set()
    reported: set[frozenset[str]] = set()

    for item in menu.items:
        if item.id in done:
            continue
        active: list[str] = []
        active_index: dict[str, int] = {}
        stack: list[tuple[str, bool]] = [(item.id, False)]
        while stack:
            item_id, exiting = stack.pop()
            if exiting:
                active.pop()
                active_index.pop(item_id)
                done.add(item_id)
                continue
            if item_id in done:
                continue
            if item_id in active_index:
                cycle = active[active_index[item_id] :] + [item_id]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    out.append(
                        CheckItem(
                            level="error",
                            rule="dependency_cycle",
                            message=(
                                "Dependency cycle: " + " -> ".join(cycle) + "."
                            ),
                        )
                    )
                continue
            active_index[item_id] = len(active)
            active.append(item_id)
            stack.append((item_id, True))
            for dep in reversed(known[item_id].dependencies):
                if dep in known:
                    stack.append((dep, False))
    return out


def _rates_gates(portfolio: Portfolio) -> list[CheckItem]:
    """Advisory rate heuristics — warnings, never funder rules."""
    out: list[CheckItem] = []
    for role in portfolio.rates.roles:
        base = role.base_usd
        loaded = role.loaded_usd
        if base and base > 0:
            factor = loaded / base
            if factor < LOAD_FACTOR_MIN:
                out.append(
                    CheckItem(
                        level="warning",
                        rule="load_factor_suspicious",
                        message=(
                            f"Role '{role.role}': loaded/base = "
                            f"{factor:.2f} — loaded is barely above "
                            f"base (pasted base as loaded?). Advisory "
                            f"heuristic, not a funder rule."
                        ),
                    )
                )
            elif factor > LOAD_FACTOR_MAX:
                factor_text = (
                    f"{factor:.2f}"
                    if math.isfinite(factor)
                    else "above the finite float range"
                )
                out.append(
                    CheckItem(
                        level="warning",
                        rule="load_factor_suspicious",
                        message=(
                            f"Role '{role.role}': loaded/base = "
                            f"{factor_text} — a load factor above "
                            f"{LOAD_FACTOR_MAX:.1f} is unusually high. "
                            f"Advisory heuristic, not a funder rule."
                        ),
                    )
                )
            if role.components:
                total = Decimal(str(base)) + sum(
                    (
                        Decimal(str(comp.amount_usd))
                        for comp in role.components
                    ),
                    Decimal(0),
                )
                delta = total - Decimal(str(loaded))
                if abs(delta) > Decimal(str(COMPONENTS_TOLERANCE_USD)):
                    out.append(
                        CheckItem(
                            level="warning",
                            rule="components_mismatch",
                            message=(
                                f"Role '{role.role}': base + components "
                                f"= {format_money(total, portfolio.rates.currency)} "
                                f"but loaded_usd = "
                                f"{format_money(loaded, portfolio.rates.currency)} "
                                f"(off by {round_half_up(delta):+,})."
                            ),
                        )
                    )
    return out


# -- 3. portfolio fraction integrity and co-funding (C2) ----------------


def _fraction_gates(portfolio: Portfolio) -> list[CheckItem]:
    """Validate every fraction used by the portfolio-wide C2 sum."""
    out: list[CheckItem] = []
    for selection in portfolio.selections:
        sid = selection.id
        for line in selection.selections:
            if line.fraction < 0 or line.fraction > 1:
                out.append(
                    CheckItem(
                        level="error",
                        rule="fraction_out_of_range",
                        message=(
                            f"Selection '{sid}' item '{line.item}' fraction "
                            f"{line.fraction!r} is outside [0, 1]."
                        ),
                        section=sid,
                    )
                )
        if selection.org_base is not None:
            base_fraction = selection.org_base.fraction
            if base_fraction < 0 or base_fraction > 1:
                out.append(
                    CheckItem(
                        level="error",
                        rule="fraction_out_of_range",
                        message=(
                            f"Selection '{sid}' org_base fraction "
                            f"{base_fraction!r} is outside [0, 1]."
                        ),
                        section=sid,
                    )
                )
    return out


def _cofunding_gate(portfolio: Portfolio) -> list[CheckItem]:
    """No item may be sold past 100% across live/awarded selections."""
    contributions: dict[str, list[tuple[str, str, float]]] = {}
    for selection in portfolio.selections:
        if selection.status not in BINDING_STATUSES:
            continue
        for line in selection.selections:
            contributions.setdefault(line.item, []).append(
                (selection.id, "", line.fraction)
            )
        if selection.org_base is not None:
            contributions.setdefault(selection.org_base.item, []).append(
                (selection.id, "org base", selection.org_base.fraction)
            )

    out: list[CheckItem] = []
    for item_id, parts in contributions.items():
        total = sum(fraction for _, _, fraction in parts)
        if total > 1.0 + COFUNDING_TOLERANCE:
            detail = " + ".join(
                f"{sid}{f' ({kind})' if kind else ''} {fraction!r}"
                for sid, kind, fraction in parts
            )
            out.append(
                CheckItem(
                    level="error",
                    rule="cofunding_over_allocated",
                    message=(
                        f"Item '{item_id}' is over-allocated across "
                        f"live/awarded selections: {detail} = "
                        f"{total!r} (max 1.0)."
                    ),
                )
            )
    return out


# -- 4. per-selection gates ---------------------------------------------


def _selection_gates(
    portfolio: Portfolio,
    selection: Selection,
    pack: Optional[FunderPack],
) -> list[CheckItem]:
    out: list[CheckItem] = []
    menu = portfolio.menu
    known_items = menu.items_by_id
    sid = selection.id

    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in selection.selections:
        if line.item not in known_items:
            out.append(
                CheckItem(
                    level="error",
                    rule="unknown_item",
                    message=(
                        f"Selection '{sid}' references unknown item "
                        f"'{line.item}'."
                    ),
                    section=sid,
                )
            )
        if line.item in seen:
            duplicates.add(line.item)
        seen.add(line.item)
    for item_id in sorted(duplicates):
        out.append(
            CheckItem(
                level="error",
                rule="selection_duplicate_item",
                message=(
                    f"Selection '{sid}' lists item '{item_id}' more "
                    f"than once."
                ),
                section=sid,
            )
        )

    if selection.org_base is not None:
        base_id = selection.org_base.item
        if base_id not in known_items:
            out.append(
                CheckItem(
                    level="error",
                    rule="unknown_item",
                    message=(
                        f"Selection '{sid}' org_base references unknown "
                        f"item '{base_id}'."
                    ),
                    section=sid,
                )
            )
        elif known_items[base_id].type != "org-base":
            out.append(
                CheckItem(
                    level="error",
                    rule="org_base_type",
                    message=(
                        f"Selection '{sid}' org_base item '{base_id}' "
                        f"has type '{known_items[base_id].type}', "
                        f"expected 'org-base'."
                    ),
                    section=sid,
                )
            )
    out += _unfunded_dependency_gate(portfolio, selection)

    # Compile-dependent gates only make sense when references resolve.
    if any(item.level == "error" for item in out):
        return out
    try:
        cost = selection_cost(selection, portfolio)
    except KeyError:  # pragma: no cover - guarded above
        return out
    except OverflowError:
        out.append(_non_finite_finding(sid))
        return out
    if _contains_non_finite_float(cost.to_dict()):
        out.append(_non_finite_finding(sid))
        return out
    currency = menu.currency
    if selection.target_usd and cost.total_usd > selection.target_usd:
        fit = cost.total_usd / selection.target_usd
        out.append(
            CheckItem(
                level="warning",
                rule="over_target",
                message=(
                    f"Selection '{sid}' compiles to "
                    f"{format_money(cost.total_usd, currency)} — "
                    f"{format_percent(fit)} of the advisory target "
                    f"{format_money(selection.target_usd, currency)} "
                    f"(a target is an "
                    f"ask, not a funder cap)."
                ),
                section=sid,
            )
        )
    out += _pack_cap_gates(selection, cost.total_usd, currency, pack)
    return out


def _unfunded_dependency_gate(
    portfolio: Portfolio, selection: Selection
) -> list[CheckItem]:
    """Warn when a funded item's dependency has no funding anywhere.

    A dependency counts as covered when it is already shipped or
    in-flight, when any live/awarded selection funds it (fraction > 0),
    or when this selection funds it itself.
    """
    known_items = portfolio.menu.items_by_id
    funded: set[str] = set()
    for other in portfolio.selections:
        if other.status in BINDING_STATUSES or other.id == selection.id:
            funded.update(
                line.item for line in other.selections if line.fraction > 0
            )
            if other.org_base is not None and other.org_base.fraction > 0:
                funded.add(other.org_base.item)

    out: list[CheckItem] = []
    claims = [(line.item, line.fraction) for line in selection.selections]
    if selection.org_base is not None:
        claims.append((selection.org_base.item, selection.org_base.fraction))
    for item_id, fraction in claims:
        if fraction <= 0 or item_id not in known_items:
            continue
        for dep in known_items[item_id].dependencies:
            dep_item = known_items.get(dep)
            if dep_item is None:
                continue  # dependency_unresolved covers this
            if dep_item.status in ("shipped", "in-flight"):
                continue
            if dep in funded:
                continue
            out.append(
                CheckItem(
                    level="warning",
                    rule="dependency_unfunded",
                    message=(
                        f"Selection '{selection.id}' funds "
                        f"'{item_id}' but its dependency '{dep}' "
                        f"({dep_item.status}) is not funded in any "
                        f"live/awarded selection — the proposal "
                        f"assumes work nobody has funded."
                    ),
                    section=selection.id,
                )
            )
    return out


def _pack_cap_gates(
    selection: Selection,
    total_usd: float,
    portfolio_currency: str,
    pack: Optional[FunderPack],
) -> list[CheckItem]:
    """Funder caps from a bound rule pack, applied to the compiled total.

    The annual figure is total x 12/window_months — a uniform-spread
    approximation, so the annual cap check is a warning, not an error.
    """
    rules = pack.budget_rules if pack else None
    if rules is None:
        return []
    out: list[CheckItem] = []
    cur = rules.currency
    sid = selection.id
    has_cap = rules.total_cap is not None or rules.annual_cap is not None
    if has_cap and portfolio_currency != cur:
        return [
            CheckItem(
                level="error",
                rule="budget_currency_mismatch",
                message=(
                    f"Selection '{sid}' compiles in {portfolio_currency}, "
                    f"but the funder caps are in {cur}; GrantKit does not "
                    "convert currencies, so cap checks were skipped."
                ),
                section=sid,
            )
        ]
    if rules.total_cap is not None and total_usd > rules.total_cap:
        over = Decimal(str(total_usd)) - Decimal(str(rules.total_cap))
        out.append(
            CheckItem(
                level="error",
                rule="budget_over_total_cap",
                message=(
                    f"Selection '{sid}' compiles to "
                    f"{format_money(total_usd, cur)}, which exceeds the "
                    f"funder cap of {format_money(rules.total_cap, cur)} "
                    f"(over by {format_money(over, cur)})."
                ),
                section=sid,
                citation=rules.notes,
            )
        )
    if rules.annual_cap is not None and selection.window_months > 0:
        annual = (
            Decimal(str(total_usd))
            * Decimal(12)
            / Decimal(selection.window_months)
        )
        if annual > Decimal(str(rules.annual_cap)):
            out.append(
                CheckItem(
                    level="warning",
                    rule="budget_over_annual_cap",
                    message=(
                        f"Selection '{sid}' annualizes to "
                        f"{format_money(annual, cur)} (total x 12/"
                        f"{selection.window_months} months), above "
                        f"the annual cap of "
                        f"{format_money(rules.annual_cap, cur)} — "
                        f"uniform-spread "
                        f"approximation; confirm against the actual "
                        f"phasing."
                    ),
                    section=sid,
                )
            )
    return out
