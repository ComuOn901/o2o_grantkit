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
from .resolve import ResolvedItem, resolve_item
from .schema import (
    SELECTION_SCHEMA_V1,
    Selection,
    ValidationIssue,
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

#: Capacity comparisons allow a small relative float tolerance.
CAPACITY_TOLERANCE_FACTOR = 1.0000001

_RESOLUTION_ERRORS = (KeyError, TypeError, ValueError, OverflowError)


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

    subject: Optional[Selection] = None
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
        subject = target
        scope = [target]
    else:
        scope = list(portfolio.selections)
    for selection in scope:
        items += _selection_gates(portfolio, selection, pack)
    items += _role_over_allocated_gate(portfolio, subject)
    return items


# -- 1. schema ----------------------------------------------------------


def _schema_gates(portfolio: Portfolio) -> list[CheckItem]:
    out: list[CheckItem] = []
    for message in validate_menu(portfolio.menu_data):
        out.append(
            CheckItem(
                level="error",
                rule=_validation_rule(message, "menu_invalid"),
                message=f"menu.yaml: {message}",
            )
        )
    for message in validate_rates(portfolio.rates_data):
        out.append(
            CheckItem(
                level="error",
                rule=_validation_rule(message, "rates_invalid"),
                message=f"rates.yaml: {message}",
            )
        )
    seen_ids: set[str] = set()
    for data, selection in zip(
        portfolio.selections_data, portfolio.selections
    ):
        sid = selection.id or "(unnamed)"
        for message in validate_selection(data, portfolio):
            out.append(
                CheckItem(
                    level="error",
                    rule=_validation_rule(message, "selection_invalid"),
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


def _validation_rule(message: str, fallback: str) -> str:
    """Use a v1 issue's precise rule without changing legacy strings."""
    if isinstance(message, ValidationIssue):
        return message.rule
    return fallback


# -- 2. menu / rates integrity ------------------------------------------


def _menu_gates(portfolio: Portfolio) -> list[CheckItem]:
    out: list[CheckItem] = []
    menu = portfolio.menu
    known_roles = set(portfolio.rates.roles_by_name)
    known_items = set(menu.items_by_id)
    provider = portfolio.rates.provider or "rates.yaml"
    resolved_items = _resolved_menu_items(portfolio, out)

    for item in menu.items:
        resolved = resolved_items.get(item.id)
        if resolved is None:
            continue
        for role in resolved.resourcing.fte_months:
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
        for roster in resolved.resourcing.roster:
            if roster.role not in known_roles:
                out.append(
                    CheckItem(
                        level="error",
                        rule="unknown_role",
                        message=(
                            f"Item '{item.id}' roster references role "
                            f"'{roster.role}', which is not present in "
                            f"the rates ({provider})."
                        ),
                    )
                )
        for unit in resolved.resourcing.units:
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
        for dep in resolved.dependencies:
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
    out += _cycle_gate(portfolio, resolved_items)
    return out


def _resolved_menu_items(
    portfolio: Portfolio,
    findings: Optional[list[CheckItem]] = None,
) -> dict[str, ResolvedItem]:
    """Resolve menu items defensively for structural and advisory gates."""
    result: dict[str, ResolvedItem] = {}
    for item in portfolio.menu.items:
        try:
            result[item.id] = resolve_item(
                item,
                portfolio.menu.kinds,
                path=f"menu.items.{item.id}",
            )
        except _RESOLUTION_ERRORS as exc:
            # Schema gates normally report the cause.  A caller may also
            # hand us a valid-looking expression whose evaluated value is
            # unusable (for example, a zero duration). Surface that at the
            # gate boundary rather than allowing the compile command to
            # traceback after validation.
            if findings is not None:
                findings.append(
                    CheckItem(
                        level="error",
                        rule=(
                            "kind_form_invalid"
                            if item.kind is not None
                            else "menu_invalid"
                        ),
                        message=(
                            f"Item '{item.id}' could not be resolved: {exc}."
                        ),
                    )
                )
            continue
    return result


def _cycle_gate(
    portfolio: Portfolio, known: dict[str, ResolvedItem]
) -> list[CheckItem]:
    """Detect dependency cycles with an iterative DFS in menu order."""
    out: list[CheckItem] = []
    done: set[str] = set()
    reported: set[frozenset[str]] = set()

    for item in portfolio.menu.items:
        if item.id in done or item.id not in known:
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
                if line.instance is not None:
                    subject = f"instance '{line.instance.id}'"
                else:
                    subject = f"item '{line.item}'"
                out.append(
                    CheckItem(
                        level="error",
                        rule="fraction_out_of_range",
                        message=(
                            f"Selection '{sid}' {subject} fraction "
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
            if line.instance is not None:
                continue
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
    resolved_menu = _resolved_menu_items(portfolio)

    seen: set[str] = set()
    duplicates: set[str] = set()
    seen_instances: set[str] = set()
    resolved_instances: dict[str, ResolvedItem] = {}
    for line in selection.selections:
        if line.instance is not None:
            instance = line.instance
            instance_id = instance.id
            if instance_id in known_items or instance_id in seen_instances:
                out.append(
                    CheckItem(
                        level="error",
                        rule="instance_id_collision",
                        message=(
                            f"Selection '{sid}' instance id "
                            f"'{instance_id}' repeats or collides with a "
                            "menu item id."
                        ),
                        section=sid,
                    )
                )
                continue
            seen_instances.add(instance_id)
            try:
                resolved_instances[instance_id] = resolve_item(
                    instance,
                    menu.kinds,
                    path=f"selection.{sid}.instances.{instance_id}",
                )
            except _RESOLUTION_ERRORS as exc:
                # Precise schema findings normally report this.  Keep the
                # integrity layer safe for manually-mutated portfolios.
                out.append(
                    CheckItem(
                        level="error",
                        rule="kind_form_invalid",
                        message=(
                            f"Selection '{sid}' instance '{instance_id}' "
                            f"could not be resolved: {exc}."
                        ),
                        section=sid,
                    )
                )
                continue
            continue
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

    known_dependency_ids = set(known_items) | set(resolved_instances)
    for instance_id, resolved in resolved_instances.items():
        out += _resolved_instance_gates(
            portfolio,
            selection,
            instance_id,
            resolved,
            known_dependency_ids,
        )
    out += _instance_cycle_gate(selection, resolved_instances)

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
        elif (
            base_id in resolved_menu
            and resolved_menu[base_id].type != "org-base"
        ):
            out.append(
                CheckItem(
                    level="error",
                    rule="org_base_type",
                    message=(
                        f"Selection '{sid}' org_base item '{base_id}' "
                        f"has type '{resolved_menu[base_id].type}', "
                        f"expected 'org-base'."
                    ),
                    section=sid,
                )
            )
    out += _unfunded_dependency_gate(
        portfolio,
        selection,
        resolved_menu,
        resolved_instances,
    )

    # Compile-dependent gates only make sense when references resolve.
    if any(item.level == "error" for item in out):
        return out
    try:
        cost = selection_cost(selection, portfolio)
    except (KeyError, TypeError, ValueError):
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
    if (
        selection.schema == SELECTION_SCHEMA_V1
        and cost.outside_window_usd > 1.0
    ):
        out.append(
            CheckItem(
                level="warning",
                rule="phase_outside_window",
                message=(
                    f"Selection '{sid}' phases "
                    f"{format_money(cost.outside_window_usd, currency)} "
                    f"outside its {selection.window_months}-month window; "
                    "the amount remains included in the compiled total."
                ),
                section=sid,
            )
        )
    out += _pack_cap_gates(selection, cost.total_usd, currency, pack)
    return out


def _resolved_instance_gates(
    portfolio: Portfolio,
    selection: Selection,
    instance_id: str,
    resolved: ResolvedItem,
    known_dependency_ids: set[str],
) -> list[CheckItem]:
    """Check concrete references contributed by one inline instance."""
    out: list[CheckItem] = []
    sid = selection.id
    provider = portfolio.rates.provider or "rates.yaml"
    known_roles = set(portfolio.rates.roles_by_name)
    for role in resolved.resourcing.fte_months:
        if role not in known_roles:
            out.append(
                CheckItem(
                    level="error",
                    rule="unknown_role",
                    message=(
                        f"Selection '{sid}' instance '{instance_id}' "
                        f"resourcing references role '{role}', which is "
                        f"not present in the rates ({provider})."
                    ),
                    section=sid,
                )
            )
    for roster in resolved.resourcing.roster:
        if roster.role not in known_roles:
            out.append(
                CheckItem(
                    level="error",
                    rule="unknown_role",
                    message=(
                        f"Selection '{sid}' instance '{instance_id}' "
                        f"roster references role '{roster.role}', which is "
                        f"not present in the rates ({provider})."
                    ),
                    section=sid,
                )
            )
    for unit in resolved.resourcing.units:
        if unit not in portfolio.menu.unit_costs:
            out.append(
                CheckItem(
                    level="error",
                    rule="unknown_unit",
                    message=(
                        f"Selection '{sid}' instance '{instance_id}' "
                        f"references unit '{unit}', which is not present "
                        "in the menu unit_costs."
                    ),
                    section=sid,
                )
            )
    for dep in resolved.dependencies:
        if dep not in known_dependency_ids:
            out.append(
                CheckItem(
                    level="error",
                    rule="dependency_unresolved",
                    message=(
                        f"Selection '{sid}' instance '{instance_id}' "
                        f"depends on unknown item '{dep}'."
                    ),
                    section=sid,
                )
            )
    return out


def _instance_cycle_gate(
    selection: Selection,
    instances: dict[str, ResolvedItem],
) -> list[CheckItem]:
    """Detect cycles among selection-private inline instances."""
    out: list[CheckItem] = []
    done: set[str] = set()
    reported: set[frozenset[str]] = set()

    for line in selection.selections:
        if line.instance is None:
            continue
        root = line.instance.id
        if root in done or root not in instances:
            continue
        active: list[str] = []
        active_index: dict[str, int] = {}
        stack: list[tuple[str, bool]] = [(root, False)]
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
                            section=selection.id,
                        )
                    )
                continue
            active_index[item_id] = len(active)
            active.append(item_id)
            stack.append((item_id, True))
            for dep in reversed(instances[item_id].dependencies):
                if dep in instances:
                    stack.append((dep, False))
    return out


def _unfunded_dependency_gate(
    portfolio: Portfolio,
    selection: Selection,
    resolved_menu: dict[str, ResolvedItem],
    resolved_instances: dict[str, ResolvedItem],
) -> list[CheckItem]:
    """Warn when a funded item's dependency has no funding anywhere.

    A dependency counts as covered when it is already shipped or
    in-flight, when any live/awarded selection funds it (fraction > 0),
    or when this selection funds it itself.
    """
    funded: set[str] = set()
    for other in portfolio.selections:
        if other.status in BINDING_STATUSES or other.id == selection.id:
            funded.update(
                line.item
                for line in other.selections
                if line.instance is None and line.fraction > 0
            )
            if other.org_base is not None and other.org_base.fraction > 0:
                funded.add(other.org_base.item)
    funded.update(
        line.instance.id
        for line in selection.selections
        if line.instance is not None and line.fraction > 0
    )

    out: list[CheckItem] = []
    known_items = dict(resolved_menu)
    known_items.update(resolved_instances)
    claims = [
        (
            line.instance.id if line.instance is not None else line.item,
            line.fraction,
        )
        for line in selection.selections
    ]
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


def _role_over_allocated_gate(
    portfolio: Portfolio, subject: Optional[Selection]
) -> list[CheckItem]:
    """Warn when relative-year staffing exceeds a declared role capacity."""
    capacities = {
        role.role: role.capacity_fte
        for role in portfolio.rates.roles
        if role.capacity_fte is not None
    }
    if not capacities:
        return []

    active = [
        selection
        for selection in portfolio.selections
        if selection.status in BINDING_STATUSES
    ]
    if (
        subject is not None
        and subject.status not in BINDING_STATUSES
        and all(selection.id != subject.id for selection in active)
    ):
        active.append(subject)

    compiled: dict[str, Any] = {}
    for selection in sorted(active, key=lambda entry: entry.id):
        try:
            compiled[selection.id] = selection_cost(selection, portfolio)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            # Referential/schema findings carry the actionable error.
            continue

    out: list[CheckItem] = []
    for role in sorted(capacities):
        capacity = float(capacities[role] or 0.0)
        period_count = max(
            (len(cost.periods) for cost in compiled.values()), default=0
        )
        for index in range(period_count):
            contributions: list[tuple[str, float]] = []
            for selection_id in sorted(compiled):
                periods = compiled[selection_id].periods
                if index >= len(periods):
                    continue
                period = periods[index]
                demand = float(period["fte_by_role"].get(role, 0.0)) + float(
                    period["base_fte_by_role"].get(role, 0.0)
                )
                if demand > 0:
                    contributions.append((selection_id, demand))
            demand_total = sum(value for _, value in contributions)
            if demand_total <= capacity * CAPACITY_TOLERANCE_FACTOR:
                continue
            detail = ", ".join(
                f"{selection_id} {demand:g} FTE"
                for selection_id, demand in contributions
            )
            out.append(
                CheckItem(
                    level="warning",
                    rule="role_over_allocated",
                    message=(
                        f"Role '{role}' in Y{index + 1} demands "
                        f"{demand_total:g} FTE versus capacity "
                        f"{capacity:g} FTE ({detail})."
                    ),
                    section=subject.id if subject is not None else None,
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
