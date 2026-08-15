"""Schemas for the budget-model documents.

Three YAML documents drive ``grantkit budget``:

* ``menu.yaml`` (``grantkit-menu/v0``) — the org's priced work-item menu:
  named unit costs, org-level overheads, and a list of work items, each with
  machine-checkable done-evidence, provenance, and a resourcing block.
* ``rates.yaml`` (``grantkit-rates/v0``) — fully-loaded personnel rates
  produced by a rates provider (see ``docs/rates-contract.md``;
  eggnest-employer is the reference provider).
* ``selection.yaml`` (``grantkit-selection/v0``) — one proposal expressed as
  a selection of menu items with funding fractions.

Each ``validate_*`` function checks a raw dict against the documented schema
and returns a list of human-readable error strings (empty list == valid), in
the same style as :func:`grantkit.packs.schema.validate_pack`. The
``from_dict`` constructors are tolerant: they assume the dict has passed
validation (or is trusted) and skip anything malformed, so loading never
raises on a parseable YAML mapping.

grantkit validates presence and types; it never recomputes a rates
provider's law-based numbers (that is the provider's job, covered by the
provider's tests), and it never invents funder limits. Economic sanity
checks (load factors, component sums) are advisory warnings emitted by
:mod:`grantkit.menu.gates`, clearly labeled as heuristics.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, TypeGuard

MENU_SCHEMA = "grantkit-menu/v0"
RATES_SCHEMA = "grantkit-rates/v0"
SELECTION_SCHEMA = "grantkit-selection/v0"

#: Item lifecycle states.
VALID_ITEM_STATUSES = {"shipped", "in-flight", "planned"}
#: Selection (proposal) lifecycle states. The co-funding gate binds
#: ``live`` and ``awarded`` selections only.
VALID_SELECTION_STATUSES = {
    "draft",
    "live",
    "awarded",
    "withdrawn",
    "declined",
}
#: Provenance basis vocabulary for rate components (exactly these).
VALID_COMPONENT_BASES = {"computed", "configured", "assumed"}
#: Recommended (not enforced) item-type vocabulary.
RECOMMENDED_ITEM_TYPES = (
    "program-coverage",
    "platform",
    "research-eval",
    "field",
    "org-base",
)

_ITEM_ID_RE = re.compile(r"^[a-z0-9-]+$")


def _is_int_or_none(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_number(value: Any) -> TypeGuard[int | float]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        # Extremely large integers cannot be represented by the float-based
        # engine and would otherwise become infinity during parsing.
        return False


def _is_number_or_none(value: Any) -> bool:
    return value is None or _is_number(value)


def _is_string(value: Any, *, nonempty: bool = False) -> TypeGuard[str]:
    if not isinstance(value, str) or (nonempty and not value):
        return False
    if any(
        (ord(char) < 32 and char not in "\t\n\r") or 0x7F <= ord(char) <= 0x9F
        for char in value
    ):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _is_optional_string(value: Any) -> bool:
    return value is None or _is_string(value)


def _is_string_list(value: Any, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(_is_string(entry, nonempty=True) for entry in value)
    )


def _as_float(value: Any, default: float = 0.0) -> float:
    return float(value) if _is_number(value) else default


def _as_optional_float(value: Any) -> Optional[float]:
    return float(value) if _is_number(value) else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry) for entry in value if isinstance(entry, str)]


def _number_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): float(val) for key, val in value.items() if _is_number(val)
    }


# -- menu.yaml ----------------------------------------------------------


@dataclass
class UnitCost:
    """A named unit price referenced by ``resourcing.units``."""

    usd_per_unit: float
    derivation: Optional[str] = None
    provenance: list[str] = field(default_factory=list)


@dataclass
class Overheads:
    """Org-level economics applied at selection level."""

    fiscal_sponsorship_rate: float = 0.0
    provenance: Optional[str] = None


@dataclass
class Resourcing:
    """How a menu item is costed. At least one costed field is present.

    ``overhead_included`` is only meaningful with ``amount_usd`` /
    ``contract_usd``: it records that the amount already contains org
    overheads, so the selection-level overhead must not re-apply to it.
    """

    fte_months: dict[str, float] = field(default_factory=dict)
    units: dict[str, float] = field(default_factory=dict)
    contract_usd: Optional[float] = None
    recurring_usd_per_year: Optional[float] = None
    amount_usd: Optional[float] = None
    overhead_included: bool = False


@dataclass
class MenuItem:
    """One priced work item on the menu."""

    id: str
    type: str
    title: str
    what: str
    evidence: str
    status: str
    resourcing: Resourcing
    duration_months: Optional[int] = None
    dependencies: list[str] = field(default_factory=list)
    revenue_unlock: Optional[str] = None
    provenance: list[str] = field(default_factory=list)


@dataclass
class Menu:
    """A fully-parsed ``menu.yaml``."""

    schema: str = MENU_SCHEMA
    currency: str = "USD"
    overheads: Overheads = field(default_factory=Overheads)
    unit_costs: dict[str, UnitCost] = field(default_factory=dict)
    items: list[MenuItem] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def items_by_id(self) -> dict[str, MenuItem]:
        return {item.id: item for item in self.items}

    def get_item(self, item_id: str) -> Optional[MenuItem]:
        return self.items_by_id.get(item_id)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Menu":
        overheads_data = data.get("overheads")
        if not isinstance(overheads_data, dict):
            overheads_data = {}
        overheads = Overheads(
            fiscal_sponsorship_rate=_as_float(
                overheads_data.get("fiscal_sponsorship_rate")
            ),
            provenance=overheads_data.get("provenance"),
        )
        unit_costs: dict[str, UnitCost] = {}
        raw_units = data.get("unit_costs")
        if isinstance(raw_units, dict):
            for name, entry in raw_units.items():
                if not isinstance(entry, dict):
                    continue
                unit_costs[str(name)] = UnitCost(
                    usd_per_unit=_as_float(entry.get("usd_per_unit")),
                    derivation=entry.get("derivation"),
                    provenance=_string_list(entry.get("provenance")),
                )
        items: list[MenuItem] = []
        raw_items = data.get("items")
        for entry in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(entry, dict):
                continue
            resourcing_data = entry.get("resourcing")
            if not isinstance(resourcing_data, dict):
                resourcing_data = {}
            resourcing = Resourcing(
                fte_months=_number_map(resourcing_data.get("fte_months")),
                units=_number_map(resourcing_data.get("units")),
                contract_usd=_as_optional_float(
                    resourcing_data.get("contract_usd")
                ),
                recurring_usd_per_year=_as_optional_float(
                    resourcing_data.get("recurring_usd_per_year")
                ),
                amount_usd=_as_optional_float(
                    resourcing_data.get("amount_usd")
                ),
                overhead_included=bool(
                    resourcing_data.get("overhead_included", False)
                ),
            )
            items.append(
                MenuItem(
                    id=str(entry.get("id", "")),
                    type=str(entry.get("type", "")),
                    title=str(entry.get("title", "")),
                    what=str(entry.get("what", "")),
                    evidence=str(entry.get("evidence", "")),
                    status=str(entry.get("status", "")),
                    resourcing=resourcing,
                    duration_months=(
                        entry.get("duration_months")
                        if _is_int_or_none(entry.get("duration_months"))
                        else None
                    ),
                    dependencies=_string_list(entry.get("dependencies")),
                    revenue_unlock=entry.get("revenue_unlock"),
                    provenance=_string_list(entry.get("provenance")),
                )
            )
        return cls(
            schema=str(data.get("schema", MENU_SCHEMA)),
            currency=str(data.get("currency", "USD")),
            overheads=overheads,
            unit_costs=unit_costs,
            items=items,
            raw=data,
        )


# -- rates.yaml ---------------------------------------------------------


@dataclass
class RateComponent:
    """One component of a fully-loaded cost, with a provenance basis."""

    name: str
    amount_usd: float
    basis: str
    source: Optional[str] = None


@dataclass
class RateBenchmark:
    """Optional market provenance for a role's rate."""

    source: Optional[str] = None
    percentile: Optional[float] = None
    value_usd: Optional[float] = None


@dataclass
class RoleRate:
    """The fully-loaded annual cost of one role."""

    role: str
    loaded_usd: float
    base_usd: Optional[float] = None
    soc: Optional[str] = None
    components: list[RateComponent] = field(default_factory=list)
    benchmark: Optional[RateBenchmark] = None
    provenance: list[str] = field(default_factory=list)


@dataclass
class Rates:
    """A fully-parsed ``rates.yaml`` (the rates contract)."""

    provider: str = ""
    generated: str = ""
    currency: str = "USD"
    schema: str = RATES_SCHEMA
    scenario: Optional[str] = None
    jurisdiction: Optional[str] = None
    method: Optional[str] = None
    roles: list[RoleRate] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def roles_by_name(self) -> dict[str, RoleRate]:
        return {role.role: role for role in self.roles}

    def get_role(self, role: str) -> Optional[RoleRate]:
        return self.roles_by_name.get(role)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rates":
        roles: list[RoleRate] = []
        raw_roles = data.get("roles")
        for entry in raw_roles if isinstance(raw_roles, list) else []:
            if not isinstance(entry, dict):
                continue
            components: list[RateComponent] = []
            raw_components = entry.get("components")
            if isinstance(raw_components, list):
                for comp in raw_components:
                    if not isinstance(comp, dict):
                        continue
                    components.append(
                        RateComponent(
                            name=str(comp.get("name", "")),
                            amount_usd=_as_float(comp.get("amount_usd")),
                            basis=str(comp.get("basis", "")),
                            source=comp.get("source"),
                        )
                    )
            benchmark: Optional[RateBenchmark] = None
            raw_benchmark = entry.get("benchmark")
            if isinstance(raw_benchmark, dict):
                benchmark = RateBenchmark(
                    source=raw_benchmark.get("source"),
                    percentile=_as_optional_float(
                        raw_benchmark.get("percentile")
                    ),
                    value_usd=_as_optional_float(
                        raw_benchmark.get("value_usd")
                    ),
                )
            roles.append(
                RoleRate(
                    role=str(entry.get("role", "")),
                    loaded_usd=_as_float(entry.get("loaded_usd")),
                    base_usd=_as_optional_float(entry.get("base_usd")),
                    soc=entry.get("soc"),
                    components=components,
                    benchmark=benchmark,
                    provenance=_string_list(entry.get("provenance")),
                )
            )
        return cls(
            schema=str(data.get("schema", RATES_SCHEMA)),
            provider=str(data.get("provider", "")),
            generated=str(data.get("generated", "")),
            scenario=data.get("scenario"),
            currency=str(data.get("currency", "USD")),
            jurisdiction=data.get("jurisdiction"),
            method=data.get("method"),
            roles=roles,
            raw=data,
        )


# -- selection.yaml -----------------------------------------------------


@dataclass
class SelectionLine:
    """One selected menu item with its funding fraction."""

    item: str
    fraction: float
    note: Optional[str] = None


@dataclass
class OrgBase:
    """A fractional claim on an org-base item."""

    item: str
    fraction: float


@dataclass
class Selection:
    """A fully-parsed ``selection.yaml`` — one proposal."""

    id: str = ""
    funder: str = ""
    status: str = "draft"
    window_months: int = 0
    schema: str = SELECTION_SCHEMA
    target_usd: Optional[float] = None
    org_base: Optional[OrgBase] = None
    selections: list[SelectionLine] = field(default_factory=list)
    notes: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Selection":
        org_base: Optional[OrgBase] = None
        raw_base = data.get("org_base")
        if isinstance(raw_base, dict):
            org_base = OrgBase(
                item=str(raw_base.get("item", "")),
                fraction=_as_float(raw_base.get("fraction")),
            )
        lines: list[SelectionLine] = []
        raw_lines = data.get("selections")
        for entry in raw_lines if isinstance(raw_lines, list) else []:
            if not isinstance(entry, dict):
                continue
            lines.append(
                SelectionLine(
                    item=str(entry.get("item", "")),
                    fraction=_as_float(entry.get("fraction")),
                    note=entry.get("note"),
                )
            )
        window = data.get("window_months")
        return cls(
            schema=str(data.get("schema", SELECTION_SCHEMA)),
            id=str(data.get("id", "")),
            funder=str(data.get("funder", "")),
            status=str(data.get("status", "")),
            target_usd=_as_optional_float(data.get("target_usd")),
            window_months=(
                window
                if isinstance(window, int) and not isinstance(window, bool)
                else 0
            ),
            org_base=org_base,
            selections=lines,
            notes=data.get("notes"),
            raw=data,
        )


# -- validation ---------------------------------------------------------


def _validate_schema_key(
    data: dict[str, Any], expected: str, errors: list[str]
) -> None:
    declared = data.get("schema")
    if declared != expected:
        errors.append(f"'schema' must be '{expected}' (got {declared!r})")


def _validate_resourcing(
    resourcing: Any, where: str, errors: list[str]
) -> None:
    if not isinstance(resourcing, dict):
        errors.append(f"{where} missing 'resourcing' mapping")
        return
    fte_months = resourcing.get("fte_months")
    if fte_months is not None:
        if not isinstance(fte_months, dict):
            errors.append(f"{where} 'fte_months' must be a mapping")
        else:
            for role, months in fte_months.items():
                if not _is_string(role, nonempty=True):
                    errors.append(
                        f"{where} 'fte_months' keys must be non-empty strings"
                    )
                if not _is_number(months) or months < 0:
                    errors.append(
                        f"{where} fte_months['{role}'] must be a "
                        f"non-negative number"
                    )
    units = resourcing.get("units")
    if units is not None:
        if not isinstance(units, dict):
            errors.append(f"{where} 'units' must be a mapping")
        else:
            for unit, count in units.items():
                if not _is_string(unit, nonempty=True):
                    errors.append(
                        f"{where} 'units' keys must be non-empty strings"
                    )
                if not _is_number(count) or count < 0:
                    errors.append(
                        f"{where} units['{unit}'] must be a "
                        f"non-negative number"
                    )
    for key in ("contract_usd", "recurring_usd_per_year", "amount_usd"):
        value = resourcing.get(key)
        if value is not None and (not _is_number(value) or value < 0):
            errors.append(
                f"{where} '{key}' must be a non-negative number or null"
            )
    if "overhead_included" in resourcing and not isinstance(
        resourcing["overhead_included"], bool
    ):
        errors.append(f"{where} 'overhead_included' must be a boolean")
    costed = (
        (isinstance(fte_months, dict) and fte_months)
        or (isinstance(units, dict) and units)
        or resourcing.get("contract_usd") is not None
        or resourcing.get("recurring_usd_per_year") is not None
        or resourcing.get("amount_usd") is not None
    )
    if not costed:
        errors.append(
            f"{where} resourcing must contain at least one costed field "
            f"(fte_months, units, contract_usd, recurring_usd_per_year, "
            f"or amount_usd)"
        )


def validate_menu(data: Any) -> list[str]:
    """Validate a raw ``menu.yaml`` dict. Empty list == valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["menu must be a mapping/dict"]
    _validate_schema_key(data, MENU_SCHEMA, errors)

    currency = data.get("currency")
    if not _is_string(currency, nonempty=True):
        errors.append("missing required key: 'currency'")

    overheads = data.get("overheads")
    if overheads is not None:
        if not isinstance(overheads, dict):
            errors.append("'overheads' must be a mapping")
        else:
            rate = overheads.get("fiscal_sponsorship_rate")
            if rate is not None and (
                not _is_number(rate) or rate < 0 or rate > 1
            ):
                errors.append(
                    "overheads.fiscal_sponsorship_rate must be a number "
                    "between 0 and 1"
                )
            if not _is_optional_string(overheads.get("provenance")):
                errors.append("overheads.provenance must be a string or null")

    unit_costs = data.get("unit_costs")
    if unit_costs is not None:
        if not isinstance(unit_costs, dict):
            errors.append("'unit_costs' must be a mapping")
        else:
            for name, entry in unit_costs.items():
                where = f"unit_costs['{name}']"
                if not _is_string(name, nonempty=True):
                    errors.append("unit_costs keys must be non-empty strings")
                if not isinstance(entry, dict):
                    errors.append(f"{where} must be a mapping")
                    continue
                price = entry.get("usd_per_unit")
                if not _is_number(price) or price < 0:
                    errors.append(
                        f"{where} 'usd_per_unit' must be a non-negative number"
                    )
                provenance = entry.get("provenance")
                if provenance is not None and not _is_string_list(provenance):
                    errors.append(
                        f"{where} 'provenance' must be a list of "
                        "non-empty strings"
                    )
                if not _is_optional_string(entry.get("derivation")):
                    errors.append(
                        f"{where} 'derivation' must be a string or null"
                    )

    items = data.get("items")
    if not isinstance(items, list):
        errors.append("'items' must be a list")
        return errors

    seen_ids: set[str] = set()
    for i, item in enumerate(items):
        where = f"items[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be a mapping")
            continue
        item_id = item.get("id")
        if not _is_string(item_id, nonempty=True):
            errors.append(f"{where} missing 'id'")
        elif not _ITEM_ID_RE.match(item_id):
            errors.append(f"{where} id {item_id!r} must match [a-z0-9-]+")
        elif item_id in seen_ids:
            errors.append(f"{where} duplicate item id '{item_id}'")
        else:
            seen_ids.add(item_id)
        label = f"{where} ('{item_id}')"
        for key in ("type", "title", "what", "evidence"):
            if not _is_string(item.get(key), nonempty=True):
                errors.append(f"{label} missing '{key}'")
        status = item.get("status")
        if not _is_string(status) or status not in VALID_ITEM_STATUSES:
            errors.append(
                f"{label} invalid status {status!r} "
                f"(allowed: {sorted(VALID_ITEM_STATUSES)})"
            )
        if not _is_int_or_none(item.get("duration_months")):
            errors.append(
                f"{label} 'duration_months' must be an integer or null"
            )
        dependencies = item.get("dependencies")
        if not isinstance(dependencies, list):
            errors.append(
                f"{label} 'dependencies' must be a list (may be empty)"
            )
        elif not all(
            _is_string(dependency, nonempty=True)
            for dependency in dependencies
        ):
            errors.append(
                f"{label} 'dependencies' must contain only non-empty strings"
            )
        provenance = item.get("provenance")
        if not _is_string_list(provenance, nonempty=True):
            errors.append(
                f"{label} 'provenance' must be a non-empty list of "
                "non-empty strings"
            )
        if not _is_optional_string(item.get("revenue_unlock")):
            errors.append(f"{label} 'revenue_unlock' must be a string or null")
        _validate_resourcing(item.get("resourcing"), label, errors)
    return errors


def validate_rates(data: Any) -> list[str]:
    """Validate a raw ``rates.yaml`` dict. Empty list == valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["rates must be a mapping/dict"]
    _validate_schema_key(data, RATES_SCHEMA, errors)

    if not _is_string(data.get("provider"), nonempty=True):
        errors.append("missing required key: 'provider'")
    generated = data.get("generated")
    if not _is_string(generated, nonempty=True):
        errors.append("missing required key: 'generated' (ISO date)")
    else:
        try:
            date.fromisoformat(generated)
        except ValueError:
            errors.append(
                f"'generated' must be an ISO date (got '{generated}')"
            )
    if not _is_string(data.get("currency"), nonempty=True):
        errors.append("missing required key: 'currency'")
    for key in ("scenario", "jurisdiction", "method"):
        if not _is_optional_string(data.get(key)):
            errors.append(f"'{key}' must be a string or null")

    roles = data.get("roles")
    if not isinstance(roles, list):
        errors.append("'roles' must be a list")
        return errors

    seen_roles: set[str] = set()
    for i, role in enumerate(roles):
        where = f"roles[{i}]"
        if not isinstance(role, dict):
            errors.append(f"{where} must be a mapping")
            continue
        name = role.get("role")
        if not _is_string(name, nonempty=True):
            errors.append(f"{where} missing 'role'")
        elif name in seen_roles:
            errors.append(f"{where} duplicate role '{name}'")
        else:
            seen_roles.add(name)
        label = f"{where} ('{name}')"
        loaded = role.get("loaded_usd")
        if not _is_number(loaded) or loaded <= 0:
            errors.append(f"{label} 'loaded_usd' must be a positive number")
        if not _is_number_or_none(role.get("base_usd")):
            errors.append(f"{label} 'base_usd' must be a number or null")
        if not _is_optional_string(role.get("soc")):
            errors.append(f"{label} 'soc' must be a string or null")
        components = role.get("components")
        if components is not None:
            if not isinstance(components, list):
                errors.append(f"{label} 'components' must be a list")
            else:
                for j, comp in enumerate(components):
                    cwhere = f"{label} components[{j}]"
                    if not isinstance(comp, dict):
                        errors.append(f"{cwhere} must be a mapping")
                        continue
                    if not _is_string(comp.get("name"), nonempty=True):
                        errors.append(f"{cwhere} missing 'name'")
                    amount = comp.get("amount_usd")
                    if not _is_number(amount) or amount < 0:
                        errors.append(
                            f"{cwhere} 'amount_usd' must be a "
                            "non-negative number"
                        )
                    basis = comp.get("basis")
                    if (
                        not _is_string(basis)
                        or basis not in VALID_COMPONENT_BASES
                    ):
                        errors.append(
                            f"{cwhere} invalid basis {basis!r} "
                            f"(allowed: {sorted(VALID_COMPONENT_BASES)})"
                        )
                    if not _is_optional_string(comp.get("source")):
                        errors.append(
                            f"{cwhere} 'source' must be a string or null"
                        )
        benchmark = role.get("benchmark")
        if benchmark is not None:
            if not isinstance(benchmark, dict):
                errors.append(f"{label} 'benchmark' must be a mapping")
            else:
                if not _is_optional_string(benchmark.get("source")):
                    errors.append(
                        f"{label} benchmark.source must be a string or null"
                    )
                for key in ("percentile", "value_usd"):
                    if not _is_number_or_none(benchmark.get(key)):
                        errors.append(
                            f"{label} benchmark.{key} must be a number "
                            f"or null"
                        )
        provenance = role.get("provenance")
        if provenance is not None and not _is_string_list(provenance):
            errors.append(
                f"{label} 'provenance' must be a list of non-empty strings"
            )
    return errors


def validate_selection(data: Any) -> list[str]:
    """Validate a raw ``selection.yaml`` dict. Empty list == valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["selection must be a mapping/dict"]
    _validate_schema_key(data, SELECTION_SCHEMA, errors)

    for key in ("id", "funder"):
        if not _is_string(data.get(key), nonempty=True):
            errors.append(f"missing required key: '{key}'")
    status = data.get("status")
    if not _is_string(status) or status not in VALID_SELECTION_STATUSES:
        errors.append(
            f"invalid status {status!r} "
            f"(allowed: {sorted(VALID_SELECTION_STATUSES)})"
        )
    target = data.get("target_usd")
    if target is not None and (not _is_number(target) or target < 0):
        errors.append("'target_usd' must be a non-negative number or null")
    window = data.get("window_months")
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or window <= 0
        or not _is_number(window)
    ):
        errors.append("'window_months' must be an integer > 0")

    org_base = data.get("org_base")
    if org_base is not None:
        if not isinstance(org_base, dict):
            errors.append("'org_base' must be a mapping")
        else:
            if not _is_string(org_base.get("item"), nonempty=True):
                errors.append("org_base missing 'item'")
            if not _is_number(org_base.get("fraction")):
                errors.append("org_base 'fraction' must be a number")

    lines = data.get("selections")
    if not isinstance(lines, list):
        errors.append("'selections' must be a list (may be empty)")
        return errors
    for i, line in enumerate(lines):
        where = f"selections[{i}]"
        if not isinstance(line, dict):
            errors.append(f"{where} must be a mapping")
            continue
        if not _is_string(line.get("item"), nonempty=True):
            errors.append(f"{where} missing 'item'")
        if not _is_number(line.get("fraction")):
            errors.append(
                f"{where} ('{line.get('item')}') 'fraction' must be "
                f"a number"
            )
        if not _is_optional_string(line.get("note")):
            errors.append(f"{where} 'note' must be a string or null")
    if not _is_optional_string(data.get("notes")):
        errors.append("'notes' must be a string or null")
    return errors
