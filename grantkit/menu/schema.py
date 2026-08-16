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

MENU_SCHEMA_V0 = "grantkit-menu/v0"
MENU_SCHEMA_V1 = "grantkit-menu/v1"
RATES_SCHEMA_V0 = "grantkit-rates/v0"
RATES_SCHEMA_V1 = "grantkit-rates/v1"
SELECTION_SCHEMA_V0 = "grantkit-selection/v0"
SELECTION_SCHEMA_V1 = "grantkit-selection/v1"

# The unqualified constants name the current schema.  The allowed sets are
# intentionally public: model producers can advertise both the current and
# legacy markers without duplicating GrantKit's compatibility policy.
MENU_SCHEMA = MENU_SCHEMA_V1
RATES_SCHEMA = RATES_SCHEMA_V1
SELECTION_SCHEMA = SELECTION_SCHEMA_V1
ALLOWED_MENU_SCHEMAS = frozenset({MENU_SCHEMA_V0, MENU_SCHEMA_V1})
ALLOWED_RATES_SCHEMAS = frozenset({RATES_SCHEMA_V0, RATES_SCHEMA_V1})
ALLOWED_SELECTION_SCHEMAS = frozenset(
    {SELECTION_SCHEMA_V0, SELECTION_SCHEMA_V1}
)
# Short aliases are convenient to callers which treat these as vocabularies.
MENU_SCHEMAS = ALLOWED_MENU_SCHEMAS
RATES_SCHEMAS = ALLOWED_RATES_SCHEMAS
SELECTION_SCHEMAS = ALLOWED_SELECTION_SCHEMAS

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


class ValidationIssue(str):
    """A string-compatible schema error carrying its gate rule.

    ``validate_*`` historically returned ``list[str]``.  Subclassing ``str``
    preserves that API (including exact equality in downstream tests) while
    allowing the gate layer to route v1 errors to their specific rule ids.
    """

    rule: str

    def __new__(cls, rule: str, message: str) -> "ValidationIssue":
        value = super().__new__(cls, message)
        value.rule = rule
        return value


def _add_error(errors: list[str], rule: str, message: str) -> None:
    errors.append(ValidationIssue(rule, message))


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


_ESTIMATE_KEYS = {"central", "low", "high", "basis", "source"}


def _estimate_validation_errors(value: Any) -> list[str]:
    """Return validation errors for one estimate object."""
    if not isinstance(value, dict):
        return ["estimate must be a mapping"]
    errors: list[str] = []
    unknown = [key for key in value if key not in _ESTIMATE_KEYS]
    if unknown:
        errors.append(
            f"estimate has unknown keys: {sorted(map(str, unknown))}"
        )
    central = value.get("central")
    if not _is_number(central) or central < 0:
        errors.append("estimate.central must be a finite non-negative number")
    low = value.get("low")
    if "low" in value and (not _is_number(low) or low < 0):
        errors.append("estimate.low must be a finite non-negative number")
    high = value.get("high")
    if "high" in value and (not _is_number(high) or high < 0):
        errors.append("estimate.high must be a finite non-negative number")
    if _is_number(central):
        if _is_number(low) and low > central:
            errors.append("estimate.low must be <= estimate.central")
        if _is_number(high) and central > high:
            errors.append("estimate.central must be <= estimate.high")
    basis = value.get("basis")
    if basis is not None and (
        not _is_string(basis) or basis not in VALID_COMPONENT_BASES
    ):
        errors.append(
            "estimate.basis must be one of "
            f"{sorted(VALID_COMPONENT_BASES)} or null"
        )
    if not _is_optional_string(value.get("source")):
        errors.append("estimate.source must be a string or null")
    return errors


def _is_estimate(value: Any) -> bool:
    return isinstance(value, dict) and "central" in value


def as_number(value: Any) -> float:
    """Resolve a plain number or estimate object to a finite float.

    Estimate objects are validated in full, rather than merely reading their
    ``central`` key.  This makes the helper safe as a public trust boundary.
    Booleans are never numbers in the budget schema.
    """
    if _is_number(value):
        return float(value)
    if isinstance(value, dict):
        errors = _estimate_validation_errors(value)
        if not errors:
            return float(value["central"])
        raise ValueError("; ".join(errors))
    raise ValueError("value must be a finite number or estimate object")


def _is_cost_number(value: Any) -> bool:
    try:
        return as_number(value) >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return as_number(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return as_number(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry) for entry in value if isinstance(entry, str)]


def _number_map(value: Any, *, estimates: bool = True) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, val in value.items():
        if estimates:
            try:
                result[str(key)] = as_number(val)
            except (TypeError, ValueError, OverflowError):
                continue
        elif _is_number(val):
            result[str(key)] = float(val)
    return result


# -- menu.yaml ----------------------------------------------------------


@dataclass
class UnitCost:
    """A named unit price referenced by ``resourcing.units``."""

    usd_per_unit: float
    derivation: Optional[str] = None
    provenance: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Overheads:
    """Org-level economics applied at selection level."""

    fiscal_sponsorship_rate: float = 0.0
    provenance: Optional[str] = None


@dataclass
class RosterLine:
    """One role in an org-base roster."""

    role: str
    fte: float
    months: Optional[float] = None


@dataclass
class NonPersonnelLine:
    """One itemized non-personnel cost in a bottoms-up org base."""

    label: str
    usd_total: Optional[float] = None
    usd_per_year: Optional[float] = None
    basis: Optional[str] = None
    source: Optional[str] = None


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
    roster: list[RosterLine] = field(default_factory=list)
    non_personnel_usd_per_year: Optional[float] = None
    non_personnel: list[NonPersonnelLine] = field(default_factory=list)


@dataclass
class RevenueStream:
    """One explicit or parametric revenue stream.

    ``price_usd`` and entries in ``volume_per_year`` are concrete floats on
    explicit items and raw FORM values on kinds.  ``raw`` always retains the
    source representation for resolution and estimate collection.
    """

    stream: str
    family: str = ""
    unit: str = ""
    price_usd: Any = 0.0
    volume_per_year: list[Any] = field(default_factory=list)
    starts: str = "completion"
    ramp_months: Optional[float] = None
    provenance: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Kind:
    """A parametric menu-item template."""

    id: str
    title: str = ""
    doc: str = ""
    type: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, Any] = field(default_factory=dict)
    # Parametric resourcing is intentionally raw: its leaves are FORMs, not
    # the concrete floats represented by ``Resourcing``.
    resourcing: dict[str, Any] = field(default_factory=dict)
    duration_months: Any = None
    dependencies: Any = field(default_factory=list)
    revenue: list[RevenueStream] = field(default_factory=list)
    title_template: Optional[str] = None
    what: str = ""
    evidence: str = ""
    status: str = "planned"
    revenue_unlock: Optional[str] = None
    provenance: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class KindPreset:
    """A named partial parameter bundle for a kind."""

    kind: str
    title: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


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
    kind: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    revenue: list[RevenueStream] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_roster(value: Any) -> list[RosterLine]:
    if not isinstance(value, list):
        return []
    result: list[RosterLine] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        fte = entry.get("fte")
        if not _is_number(fte):
            continue
        months = entry.get("months")
        result.append(
            RosterLine(
                role=str(entry.get("role", "")),
                fte=float(fte),
                months=float(months) if _is_number(months) else None,
            )
        )
    return result


def _parse_non_personnel(value: Any) -> list[NonPersonnelLine]:
    if not isinstance(value, list):
        return []
    result: list[NonPersonnelLine] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        result.append(
            NonPersonnelLine(
                label=str(entry.get("label", "")),
                usd_total=_as_optional_float(entry.get("usd_total")),
                usd_per_year=_as_optional_float(entry.get("usd_per_year")),
                basis=(
                    str(entry["basis"])
                    if entry.get("basis") is not None
                    else None
                ),
                source=(
                    str(entry["source"])
                    if entry.get("source") is not None
                    else None
                ),
            )
        )
    return result


def _parse_resourcing(value: Any) -> Resourcing:
    data = value if isinstance(value, dict) else {}
    return Resourcing(
        fte_months=_number_map(data.get("fte_months")),
        units=_number_map(data.get("units"), estimates=False),
        contract_usd=_as_optional_float(data.get("contract_usd")),
        recurring_usd_per_year=_as_optional_float(
            data.get("recurring_usd_per_year")
        ),
        amount_usd=_as_optional_float(data.get("amount_usd")),
        overhead_included=bool(data.get("overhead_included", False)),
        roster=_parse_roster(data.get("roster")),
        non_personnel_usd_per_year=_as_optional_float(
            data.get("non_personnel_usd_per_year")
        ),
        non_personnel=_parse_non_personnel(data.get("non_personnel")),
    )


def _parse_revenue(value: Any, *, parametric: bool) -> list[RevenueStream]:
    if not isinstance(value, list):
        return []
    result: list[RevenueStream] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        raw_volume = entry.get("volume_per_year")
        volume = list(raw_volume) if isinstance(raw_volume, list) else []
        if not parametric:
            concrete: list[float] = []
            for amount in volume:
                try:
                    concrete.append(as_number(amount))
                except (TypeError, ValueError, OverflowError):
                    continue
            volume = concrete
        raw_price = entry.get("price_usd", 0.0)
        price: Any = raw_price
        if not parametric:
            price = _as_float(raw_price)
        ramp = entry.get("ramp_months")
        result.append(
            RevenueStream(
                stream=str(entry.get("stream", "")),
                family=str(entry.get("family", "")),
                unit=str(entry.get("unit", "")),
                price_usd=price,
                volume_per_year=volume,
                starts=str(entry.get("starts", "completion")),
                ramp_months=float(ramp) if _is_number(ramp) else None,
                provenance=_string_list(entry.get("provenance")),
                raw=entry,
            )
        )
    return result


def _parse_kind(kind_id: Any, value: Any) -> Optional[Kind]:
    if not isinstance(value, dict):
        return None
    params = value.get("params")
    derived = value.get("derived")
    resourcing = value.get("resourcing")
    return Kind(
        id=str(kind_id),
        title=str(value.get("title", "")),
        doc=str(value.get("doc", "")),
        type=str(value.get("type", kind_id)),
        params=dict(params) if isinstance(params, dict) else {},
        derived=dict(derived) if isinstance(derived, dict) else {},
        resourcing=(dict(resourcing) if isinstance(resourcing, dict) else {}),
        duration_months=value.get("duration_months"),
        dependencies=value.get("dependencies", []),
        revenue=_parse_revenue(value.get("revenue"), parametric=True),
        title_template=value.get("title_template"),
        what=str(value.get("what", "")),
        evidence=str(value.get("evidence", "")),
        status=str(value.get("status", "planned")),
        revenue_unlock=value.get("revenue_unlock"),
        provenance=_string_list(value.get("provenance")),
        raw=value,
    )


@dataclass
class Menu:
    """A fully-parsed ``menu.yaml``."""

    schema: str = MENU_SCHEMA
    currency: str = "USD"
    overheads: Overheads = field(default_factory=Overheads)
    unit_costs: dict[str, UnitCost] = field(default_factory=dict)
    items: list[MenuItem] = field(default_factory=list)
    kinds: dict[str, Kind] = field(default_factory=dict)
    kind_presets: dict[str, KindPreset] = field(default_factory=dict)
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
                    raw=entry,
                )
        kinds: dict[str, Kind] = {}
        raw_kinds = data.get("kinds")
        if isinstance(raw_kinds, dict):
            for kind_id, entry in raw_kinds.items():
                parsed = _parse_kind(kind_id, entry)
                if parsed is not None:
                    kinds[str(kind_id)] = parsed
        kind_presets: dict[str, KindPreset] = {}
        raw_presets = data.get("kind_presets")
        if isinstance(raw_presets, dict):
            for name, entry in raw_presets.items():
                if not isinstance(entry, dict):
                    continue
                params = entry.get("params")
                kind_presets[str(name)] = KindPreset(
                    kind=str(entry.get("kind", "")),
                    title=str(entry.get("title", "")),
                    params=dict(params) if isinstance(params, dict) else {},
                    raw=entry,
                )
        items: list[MenuItem] = []
        raw_items = data.get("items")
        for entry in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(entry, dict):
                continue
            resourcing = _parse_resourcing(entry.get("resourcing"))
            params = entry.get("params")
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
                    kind=(
                        str(entry.get("kind"))
                        if entry.get("kind") is not None
                        else None
                    ),
                    params=dict(params) if isinstance(params, dict) else {},
                    revenue=_parse_revenue(
                        entry.get("revenue"), parametric=False
                    ),
                    raw=entry,
                )
            )
        return cls(
            schema=str(data.get("schema", MENU_SCHEMA)),
            currency=str(data.get("currency", "USD")),
            overheads=overheads,
            unit_costs=unit_costs,
            items=items,
            kinds=kinds,
            kind_presets=kind_presets,
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
    capacity_fte: Optional[float] = None
    loaded_usd_estimate: Optional[dict[str, Any]] = None
    raw: dict[str, Any] = field(default_factory=dict)


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
                    capacity_fte=(
                        float(entry["capacity_fte"])
                        if _is_number(entry.get("capacity_fte"))
                        else None
                    ),
                    loaded_usd_estimate=(
                        dict(entry["loaded_usd"])
                        if _is_estimate(entry.get("loaded_usd"))
                        else None
                    ),
                    raw=entry,
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
class InlineInstance:
    """A selection-private instance of a parametric kind."""

    id: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    type: Optional[str] = None
    resourcing: Optional[Resourcing] = None
    duration_months: Optional[int] = None
    dependencies: list[str] = field(default_factory=list)
    revenue: list[RevenueStream] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_inline_instance(value: Any) -> Optional[InlineInstance]:
    if not isinstance(value, dict):
        return None
    params = value.get("params")
    raw_resourcing = value.get("resourcing")
    duration = value.get("duration_months")
    return InlineInstance(
        id=str(value.get("id", "")),
        kind=str(value.get("kind", "")),
        params=dict(params) if isinstance(params, dict) else {},
        title=value.get("title"),
        type=value.get("type"),
        resourcing=(
            _parse_resourcing(raw_resourcing)
            if isinstance(raw_resourcing, dict)
            else None
        ),
        duration_months=(duration if _is_int_or_none(duration) else None),
        dependencies=_string_list(value.get("dependencies")),
        revenue=_parse_revenue(value.get("revenue"), parametric=False),
        provenance=_string_list(value.get("provenance")),
        raw=value,
    )


@dataclass
class SelectionLine:
    """One selected menu item with its funding fraction."""

    item: str = ""
    fraction: float = 0.0
    note: Optional[str] = None
    instance: Optional[InlineInstance] = None
    start_month: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


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
    horizon_months: int = 0
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
                    instance=_parse_inline_instance(entry.get("instance")),
                    start_month=(
                        entry.get("start_month", 0)
                        if isinstance(entry.get("start_month", 0), int)
                        and not isinstance(entry.get("start_month", 0), bool)
                        else 0
                    ),
                    raw=entry,
                )
            )
        window = data.get("window_months")
        parsed_window = (
            window
            if isinstance(window, int) and not isinstance(window, bool)
            else 0
        )
        horizon = data.get("horizon_months", parsed_window)
        return cls(
            schema=str(data.get("schema", SELECTION_SCHEMA)),
            id=str(data.get("id", "")),
            funder=str(data.get("funder", "")),
            status=str(data.get("status", "")),
            target_usd=_as_optional_float(data.get("target_usd")),
            window_months=parsed_window,
            org_base=org_base,
            selections=lines,
            notes=data.get("notes"),
            horizon_months=(
                horizon
                if isinstance(horizon, int) and not isinstance(horizon, bool)
                else parsed_window
            ),
            raw=data,
        )


# -- validation ---------------------------------------------------------


def _validate_schema_key(
    data: dict[str, Any], allowed: frozenset[str], errors: list[str], rule: str
) -> None:
    declared = data.get("schema")
    if declared not in allowed:
        _add_error(
            errors,
            rule,
            f"'schema' must be one of {sorted(allowed)} (got {declared!r})",
        )


def _first_form_estimate_path(value: Any, path: str) -> Optional[str]:
    """Find estimates at FORM scalar sites without scanning identifier keys."""
    if isinstance(value, list):
        for index, entry in enumerate(value):
            found = _first_form_estimate_path(entry, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    if not isinstance(value, dict):
        return None
    if set(value) & _ESTIMATE_KEYS:
        return path
    if isinstance(value.get("const"), dict):
        return f"{path}.const"
    per = value.get("per")
    if isinstance(per, dict):
        for param, coefficient in per.items():
            if isinstance(coefficient, dict):
                return f"{path}.per[{param!r}]"
    by = value.get("by")
    if isinstance(by, dict):
        for param, choices in by.items():
            if not isinstance(choices, dict):
                continue
            for choice, coefficient in choices.items():
                if isinstance(coefficient, dict):
                    return f"{path}.by[{param!r}][{choice!r}]"
    return None


def _first_resourcing_estimate_path(
    resourcing: Any, path: str, *, parametric: bool
) -> Optional[str]:
    """Find the first estimate in concrete or FORM resourcing leaves."""
    if not isinstance(resourcing, dict):
        return None
    mapping_fields = ("fte_months", "units") if parametric else ("fte_months",)
    for field_name in mapping_fields:
        values = resourcing.get(field_name)
        if not isinstance(values, dict):
            continue
        for name, value in values.items():
            value_path = f"{path}.{field_name}[{name!r}]"
            if parametric:
                found = _first_form_estimate_path(value, value_path)
                if found is not None:
                    return found
            elif isinstance(value, dict):
                return value_path
    for field_name in (
        "contract_usd",
        "recurring_usd_per_year",
        "amount_usd",
        "non_personnel_usd_per_year",
    ):
        value = resourcing.get(field_name)
        value_path = f"{path}.{field_name}"
        if parametric:
            found = _first_form_estimate_path(value, value_path)
            if found is not None:
                return found
        elif isinstance(value, dict):
            return value_path
    return None


def _first_revenue_estimate_path(
    revenue: Any, path: str, *, parametric: bool
) -> Optional[str]:
    """Find the first estimate in explicit or parametric revenue."""
    if not isinstance(revenue, list):
        return None
    for stream_index, stream in enumerate(revenue):
        if not isinstance(stream, dict):
            continue
        stream_path = f"{path}[{stream_index}]"
        price = stream.get("price_usd")
        if parametric:
            found = _first_form_estimate_path(
                price, f"{stream_path}.price_usd"
            )
            if found is not None:
                return found
        elif isinstance(price, dict):
            return f"{stream_path}.price_usd"
        volume = stream.get("volume_per_year")
        if not isinstance(volume, list):
            continue
        for year, amount in enumerate(volume):
            amount_path = f"{stream_path}.volume_per_year[{year}]"
            if parametric:
                found = _first_form_estimate_path(amount, amount_path)
                if found is not None:
                    return found
            elif isinstance(amount, dict):
                return amount_path
    return None


def _first_menu_estimate_path(data: dict[str, Any]) -> Optional[str]:
    """Find an estimate only at menu fields where one is meaningful."""
    unit_costs = data.get("unit_costs")
    if isinstance(unit_costs, dict):
        for name, entry in unit_costs.items():
            if isinstance(entry, dict) and isinstance(
                entry.get("usd_per_unit"), dict
            ):
                return f"unit_costs[{name!r}].usd_per_unit"

    kinds = data.get("kinds")
    if isinstance(kinds, dict):
        for name, kind in kinds.items():
            if not isinstance(kind, dict):
                continue
            kind_path = f"kinds[{name!r}]"
            found = _first_resourcing_estimate_path(
                kind.get("resourcing"),
                f"{kind_path}.resourcing",
                parametric=True,
            )
            if found is not None:
                return found
            found = _first_form_estimate_path(
                kind.get("duration_months"),
                f"{kind_path}.duration_months",
            )
            if found is not None:
                return found
            found = _first_revenue_estimate_path(
                kind.get("revenue"),
                f"{kind_path}.revenue",
                parametric=True,
            )
            if found is not None:
                return found

    items = data.get("items")
    if not isinstance(items, list):
        return None
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_path = f"items[{index}]"
        found = _first_resourcing_estimate_path(
            item.get("resourcing"),
            f"{item_path}.resourcing",
            parametric=False,
        )
        if found is not None:
            return found
        found = _first_revenue_estimate_path(
            item.get("revenue"),
            f"{item_path}.revenue",
            parametric=False,
        )
        if found is not None:
            return found
    return None


def _first_selection_estimate_path(data: dict[str, Any]) -> Optional[str]:
    """Find estimates in selection-private instance override sites."""
    lines = data.get("selections")
    if not isinstance(lines, list):
        return None
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            continue
        instance = line.get("instance")
        if not isinstance(instance, dict):
            continue
        instance_path = f"selections[{index}].instance"
        found = _first_resourcing_estimate_path(
            instance.get("resourcing"),
            f"{instance_path}.resourcing",
            parametric=False,
        )
        if found is not None:
            return found
        found = _first_revenue_estimate_path(
            instance.get("revenue"),
            f"{instance_path}.revenue",
            parametric=False,
        )
        if found is not None:
            return found
    return None


def _first_rates_estimate_path(data: dict[str, Any]) -> Optional[str]:
    """Find an estimate only at rates fields where one is meaningful."""
    roles = data.get("roles")
    if not isinstance(roles, list):
        return None
    for index, role in enumerate(roles):
        if not isinstance(role, dict):
            continue
        role_path = f"roles[{index}]"
        for field_name in ("loaded_usd", "base_usd"):
            if isinstance(role.get(field_name), dict):
                return f"{role_path}.{field_name}"
        components = role.get("components")
        if isinstance(components, list):
            for component_index, component in enumerate(components):
                if isinstance(component, dict) and isinstance(
                    component.get("amount_usd"), dict
                ):
                    return (
                        f"{role_path}.components[{component_index}]."
                        "amount_usd"
                    )
        benchmark = role.get("benchmark")
        if isinstance(benchmark, dict) and isinstance(
            benchmark.get("value_usd"), dict
        ):
            return f"{role_path}.benchmark.value_usd"
    return None


def _require_v1_construct(
    errors: list[str],
    seen: set[str],
    *,
    rule: str,
    construct: str,
    where: str,
    required_schema: str,
) -> None:
    """Report one v1-only construct once for a legacy document."""
    if construct in seen:
        return
    seen.add(construct)
    _add_error(
        errors,
        rule,
        f"{where} uses v1-only construct '{construct}'; set 'schema' to "
        f"'{required_schema}'",
    )


def _validate_menu_schema_version(
    data: dict[str, Any], errors: list[str]
) -> None:
    """Reject menu-v1 constructs mislabeled with the v0 marker."""
    if data.get("schema") != MENU_SCHEMA_V0:
        return
    seen: set[str] = set()
    for construct in ("kinds", "kind_presets"):
        if construct in data:
            _require_v1_construct(
                errors,
                seen,
                rule="menu_invalid",
                construct=construct,
                where=construct,
                required_schema=MENU_SCHEMA_V1,
            )
    raw_kinds = data.get("kinds")
    if isinstance(raw_kinds, dict):
        for kind_id, kind in raw_kinds.items():
            if isinstance(kind, dict) and "revenue" in kind:
                _require_v1_construct(
                    errors,
                    seen,
                    rule="menu_invalid",
                    construct="revenue",
                    where=f"kinds[{kind_id!r}].revenue",
                    required_schema=MENU_SCHEMA_V1,
                )
    items = data.get("items")
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            where = f"items[{index}]"
            for construct in ("kind", "params", "revenue"):
                if construct in item:
                    _require_v1_construct(
                        errors,
                        seen,
                        rule="menu_invalid",
                        construct=construct,
                        where=f"{where}.{construct}",
                        required_schema=MENU_SCHEMA_V1,
                    )
            resourcing = item.get("resourcing")
            if isinstance(resourcing, dict):
                for construct in (
                    "roster",
                    "non_personnel_usd_per_year",
                    "non_personnel",
                ):
                    if construct in resourcing:
                        _require_v1_construct(
                            errors,
                            seen,
                            rule="menu_invalid",
                            construct=construct,
                            where=f"{where}.resourcing.{construct}",
                            required_schema=MENU_SCHEMA_V1,
                        )
    estimate_path = _first_menu_estimate_path(data)
    if estimate_path is not None:
        _require_v1_construct(
            errors,
            seen,
            rule="menu_invalid",
            construct="estimate",
            where=estimate_path,
            required_schema=MENU_SCHEMA_V1,
        )


def _validate_rates_schema_version(
    data: dict[str, Any], errors: list[str]
) -> None:
    """Reject rates-v1 constructs mislabeled with the v0 marker."""
    if data.get("schema") != RATES_SCHEMA_V0:
        return
    seen: set[str] = set()
    roles = data.get("roles")
    if isinstance(roles, list):
        for index, role in enumerate(roles):
            if isinstance(role, dict) and "capacity_fte" in role:
                _require_v1_construct(
                    errors,
                    seen,
                    rule="rates_invalid",
                    construct="capacity_fte",
                    where=f"roles[{index}].capacity_fte",
                    required_schema=RATES_SCHEMA_V1,
                )
    estimate_path = _first_rates_estimate_path(data)
    if estimate_path is not None:
        _require_v1_construct(
            errors,
            seen,
            rule="rates_invalid",
            construct="estimate",
            where=estimate_path,
            required_schema=RATES_SCHEMA_V1,
        )


def _validate_selection_schema_version(
    data: dict[str, Any], errors: list[str]
) -> None:
    """Reject selection-v1 constructs mislabeled with the v0 marker."""
    if data.get("schema") != SELECTION_SCHEMA_V0:
        return
    seen: set[str] = set()
    if "horizon_months" in data:
        _require_v1_construct(
            errors,
            seen,
            rule="selection_invalid",
            construct="horizon_months",
            where="horizon_months",
            required_schema=SELECTION_SCHEMA_V1,
        )
    lines = data.get("selections")
    if isinstance(lines, list):
        for index, line in enumerate(lines):
            if not isinstance(line, dict):
                continue
            for construct in ("start_month", "instance"):
                if construct in line:
                    _require_v1_construct(
                        errors,
                        seen,
                        rule="selection_invalid",
                        construct=construct,
                        where=f"selections[{index}].{construct}",
                        required_schema=SELECTION_SCHEMA_V1,
                    )
            instance = line.get("instance")
            if isinstance(instance, dict) and "revenue" in instance:
                _require_v1_construct(
                    errors,
                    seen,
                    rule="selection_invalid",
                    construct="revenue",
                    where=f"selections[{index}].instance.revenue",
                    required_schema=SELECTION_SCHEMA_V1,
                )
    estimate_path = _first_selection_estimate_path(data)
    if estimate_path is not None:
        _require_v1_construct(
            errors,
            seen,
            rule="selection_invalid",
            construct="estimate",
            where=estimate_path,
            required_schema=SELECTION_SCHEMA_V1,
        )


def _validate_cost_scalar(
    value: Any,
    where: str,
    errors: list[str],
    *,
    regular_rule: str,
    positive: bool = False,
) -> bool:
    """Validate one concrete cost scalar and assign estimate errors."""
    if isinstance(value, dict):
        estimate_errors = _estimate_validation_errors(value)
        for message in estimate_errors:
            _add_error(errors, "estimate_invalid", f"{where}: {message}")
        if estimate_errors:
            return False
        number = float(value["central"])
    elif _is_number(value):
        number = float(value)
    else:
        _add_error(
            errors,
            regular_rule,
            f"{where} must be a finite non-negative number or estimate",
        )
        return False
    if number < 0 or (positive and number <= 0):
        adjective = "positive" if positive else "non-negative"
        _add_error(
            errors,
            regular_rule,
            f"{where} must be a {adjective} number or estimate",
        )
        return False
    return True


def _validate_non_personnel(value: Any, where: str, errors: list[str]) -> None:
    """Validate itemized non-personnel lines for one resourcing block."""
    if not isinstance(value, list):
        errors.append(f"{where} 'non_personnel' must be a list")
        return
    labels: set[str] = set()
    for index, line in enumerate(value):
        nwhere = f"{where} non_personnel[{index}]"
        if not isinstance(line, dict):
            errors.append(f"{nwhere} must be a mapping")
            continue
        label = line.get("label")
        if not _is_string(label, nonempty=True) or not label.strip():
            errors.append(f"{nwhere} missing non-empty 'label'")
        else:
            normalized = label.strip()
            if normalized in labels:
                errors.append(
                    f"{where} non_personnel labels must be unique "
                    f"(duplicate {normalized!r})"
                )
            labels.add(normalized)

        present = [key for key in ("usd_total", "usd_per_year") if key in line]
        if len(present) != 1:
            errors.append(
                f"{nwhere} must contain exactly one of 'usd_total' or "
                "'usd_per_year'"
            )
        for key in present:
            amount = line[key]
            if not _is_number(amount) or amount < 0:
                errors.append(
                    f"{nwhere} '{key}' must be a finite non-negative number"
                )

        basis = line.get("basis")
        if basis is not None and (
            not _is_string(basis) or basis not in VALID_COMPONENT_BASES
        ):
            errors.append(
                f"{nwhere} 'basis' must be one of "
                f"{sorted(VALID_COMPONENT_BASES)} or null"
            )
        if not _is_optional_string(line.get("source")):
            errors.append(f"{nwhere} 'source' must be a string or null")


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
                _validate_cost_scalar(
                    months,
                    f"{where} fte_months['{role}']",
                    errors,
                    regular_rule="menu_invalid",
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
        if value is not None:
            _validate_cost_scalar(
                value,
                f"{where} '{key}'",
                errors,
                regular_rule="menu_invalid",
            )
    non_personnel = resourcing.get("non_personnel_usd_per_year")
    if non_personnel is not None:
        _validate_cost_scalar(
            non_personnel,
            f"{where} 'non_personnel_usd_per_year'",
            errors,
            regular_rule="menu_invalid",
        )
    itemized_non_personnel = resourcing.get("non_personnel")
    if itemized_non_personnel is not None:
        _validate_non_personnel(itemized_non_personnel, where, errors)
    if (
        non_personnel is not None
        and isinstance(itemized_non_personnel, list)
        and itemized_non_personnel
    ):
        errors.append(
            f"{where} cannot mix 'non_personnel_usd_per_year' with "
            "itemized 'non_personnel'"
        )
    roster = resourcing.get("roster")
    if roster is not None:
        if not isinstance(roster, list):
            errors.append(f"{where} 'roster' must be a list")
        else:
            for index, line in enumerate(roster):
                rwhere = f"{where} roster[{index}]"
                if not isinstance(line, dict):
                    errors.append(f"{rwhere} must be a mapping")
                    continue
                if not _is_string(line.get("role"), nonempty=True):
                    errors.append(f"{rwhere} missing 'role'")
                fte = line.get("fte")
                if not _is_number(fte) or fte < 0:
                    errors.append(
                        f"{rwhere} 'fte' must be a non-negative number"
                    )
                months = line.get("months")
                if months is not None and (
                    not _is_number(months) or months < 0
                ):
                    errors.append(
                        f"{rwhere} 'months' must be a non-negative "
                        "number or null"
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
        or (isinstance(roster, list) and roster)
        or resourcing.get("non_personnel_usd_per_year") is not None
        or (
            isinstance(itemized_non_personnel, list) and itemized_non_personnel
        )
    )
    if not costed:
        errors.append(
            f"{where} resourcing must contain at least one costed field "
            f"(fte_months, units, contract_usd, recurring_usd_per_year, "
            f"amount_usd, roster, non_personnel, or "
            f"non_personnel_usd_per_year)"
        )


_PARAM_TYPES = {"number", "integer", "enum", "boolean", "string"}
_FORM_KEYS = {"const", "per", "by", "when"}


def _same_literal(left: Any, right: Any) -> bool:
    """Compare enum/boolean literals without Python's bool == int quirk."""
    return type(left) is type(right) and left == right


def _literal_in(value: Any, choices: list[Any]) -> bool:
    return any(_same_literal(value, choice) for choice in choices)


def _param_value_valid(value: Any, definition: dict[str, Any]) -> bool:
    param_type = definition.get("type")
    if param_type == "number":
        valid = _is_number(value)
    elif param_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif param_type == "boolean":
        valid = isinstance(value, bool)
    elif param_type == "string":
        valid = _is_string(value)
    elif param_type == "enum":
        choices = definition.get("values")
        valid = isinstance(choices, list) and _literal_in(value, choices)
    else:
        return False
    if not valid:
        return False
    if param_type in {"number", "integer"}:
        minimum = definition.get("min")
        if minimum is None:
            minimum = 0
        maximum = definition.get("max")
        if _is_number(minimum) and value < minimum:
            return False
        if _is_number(maximum) and value > maximum:
            return False
    return True


def _validate_param_definitions(
    value: Any, where: str, errors: list[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        _add_error(
            errors,
            "kind_param_invalid",
            f"{where} 'params' must be a mapping",
        )
        return {}
    definitions: dict[str, dict[str, Any]] = {}
    for name, definition in value.items():
        pwhere = f"{where} params['{name}']"
        if not _is_string(name, nonempty=True):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{where} param names must be non-empty strings",
            )
            continue
        if not isinstance(definition, dict):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{pwhere} must be a mapping",
            )
            continue
        definitions[name] = definition
        param_type = definition.get("type")
        if param_type not in _PARAM_TYPES:
            _add_error(
                errors,
                "kind_param_invalid",
                f"{pwhere} invalid type {param_type!r}",
            )
        if param_type == "enum":
            choices = definition.get("values")
            if not isinstance(choices, list) or not choices:
                _add_error(
                    errors,
                    "kind_param_invalid",
                    f"{pwhere} enum 'values' must be a non-empty list",
                )
            elif any(
                _same_literal(a, b)
                for index, a in enumerate(choices)
                for b in choices[index + 1 :]
            ):
                _add_error(
                    errors,
                    "kind_param_invalid",
                    f"{pwhere} enum values must be unique",
                )
        for bound in ("min", "max"):
            bound_value = definition.get(bound)
            if bound_value is not None and (
                param_type not in {"number", "integer"}
                or not _is_number(bound_value)
            ):
                _add_error(
                    errors,
                    "kind_param_invalid",
                    f"{pwhere} '{bound}' is only valid as a finite number "
                    "on number/integer params",
                )
        minimum = definition.get("min")
        maximum = definition.get("max")
        if _is_number(minimum) and _is_number(maximum) and minimum > maximum:
            _add_error(
                errors,
                "kind_param_invalid",
                f"{pwhere} min must be <= max",
            )
        if "default" not in definition:
            _add_error(
                errors,
                "kind_param_invalid",
                f"{pwhere} missing required 'default'",
            )
        elif not _param_value_valid(definition["default"], definition):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{pwhere} default is invalid or outside its bounds",
            )
        for text_key in ("unit", "doc"):
            if not _is_optional_string(definition.get(text_key)):
                _add_error(
                    errors,
                    "kind_param_invalid",
                    f"{pwhere} '{text_key}' must be a string or null",
                )
    return definitions


def _validate_param_values(
    value: Any,
    definitions: dict[str, dict[str, Any]],
    where: str,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        _add_error(
            errors,
            "kind_param_invalid",
            f"{where} 'params' must be a mapping",
        )
        return
    for name, param_value in value.items():
        if name not in definitions:
            _add_error(
                errors,
                "kind_param_invalid",
                f"{where} undeclared param {name!r}",
            )
        elif not _param_value_valid(param_value, definitions[name]):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{where} param {name!r} has an invalid type or is "
                "outside its bounds",
            )


def _validate_derived(
    value: Any,
    definitions: dict[str, dict[str, Any]],
    where: str,
    errors: list[str],
) -> set[str]:
    numeric = {
        name
        for name, definition in definitions.items()
        if definition.get("type") in {"number", "integer"}
    }
    if value is None:
        return numeric
    if not isinstance(value, dict):
        _add_error(
            errors,
            "derived_invalid",
            f"{where} 'derived' must be a mapping",
        )
        return numeric
    for name, expression in value.items():
        dwhere = f"{where} derived['{name}']"
        valid_name = _is_string(name, nonempty=True)
        if not valid_name or name in definitions:
            _add_error(
                errors,
                "derived_invalid",
                f"{dwhere} must have a non-empty name that does not "
                "shadow a param",
            )
            continue
        if not isinstance(expression, dict):
            _add_error(
                errors,
                "derived_invalid",
                f"{dwhere} must be a mapping",
            )
            continue
        operations = [key for key in ("product", "sum") if key in expression]
        if len(operations) != 1 or len(expression) != 1:
            _add_error(
                errors,
                "derived_invalid",
                f"{dwhere} must contain exactly one of 'product' or 'sum'",
            )
            continue
        operands = expression[operations[0]]
        if not isinstance(operands, list) or not operands:
            _add_error(
                errors,
                "derived_invalid",
                f"{dwhere} operands must be a non-empty list",
            )
            continue
        valid = True
        for operand in operands:
            if _is_number(operand):
                continue
            if not isinstance(operand, str) or operand not in numeric:
                _add_error(
                    errors,
                    "derived_invalid",
                    f"{dwhere} references unknown, non-numeric, or "
                    f"not-yet-declared operand {operand!r}",
                )
                valid = False
        if valid:
            numeric.add(name)
    return numeric


def _validate_form(
    value: Any,
    definitions: dict[str, dict[str, Any]],
    numeric_refs: set[str],
    where: str,
    errors: list[str],
    *,
    allow_list: bool = True,
) -> None:
    if isinstance(value, list):
        if not allow_list or not value:
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} must be a FORM or a non-empty list of FORMs",
            )
            return
        for index, form in enumerate(value):
            _validate_form(
                form,
                definitions,
                numeric_refs,
                f"{where}[{index}]",
                errors,
                allow_list=False,
            )
        return
    if _is_number(value):
        if value < 0:
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} must be non-negative",
            )
        return
    if isinstance(value, dict) and set(value) & _ESTIMATE_KEYS:
        _validate_cost_scalar(
            value,
            where,
            errors,
            regular_rule="kind_form_invalid",
        )
        return
    if not isinstance(value, dict):
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} must be a number, estimate, FORM, or list of FORMs",
        )
        return
    unknown = set(value) - _FORM_KEYS
    if unknown or not any(key in value for key in ("const", "per", "by")):
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} has invalid FORM keys or no value-producing term",
        )
    if "const" in value:
        _validate_cost_scalar(
            value["const"],
            f"{where}.const",
            errors,
            regular_rule="kind_form_invalid",
        )
    per = value.get("per")
    if per is not None:
        if not isinstance(per, dict):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where}.per must be a mapping",
            )
        else:
            for param, coefficient in per.items():
                if param not in numeric_refs:
                    _add_error(
                        errors,
                        "kind_form_invalid",
                        f"{where}.per references unknown or non-numeric "
                        f"param {param!r}",
                    )
                _validate_cost_scalar(
                    coefficient,
                    f"{where}.per['{param}']",
                    errors,
                    regular_rule="kind_form_invalid",
                )
    for selector_key in ("by", "when"):
        selectors = value.get(selector_key)
        if selectors is None:
            continue
        if not isinstance(selectors, dict) or not selectors:
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where}.{selector_key} must be a non-empty mapping",
            )
            continue
        for param, choices in selectors.items():
            definition = definitions.get(param, {})
            param_type = definition.get("type")
            allowed = (
                definition.get("values", [])
                if param_type == "enum"
                else [False, True]
            )
            if param_type not in {"enum", "boolean"}:
                _add_error(
                    errors,
                    "kind_form_invalid",
                    f"{where}.{selector_key} references non-enum param "
                    f"{param!r}",
                )
            if selector_key == "when":
                if not isinstance(choices, list) or not choices:
                    _add_error(
                        errors,
                        "kind_form_invalid",
                        f"{where}.when['{param}'] must be a non-empty list",
                    )
                elif any(
                    not _literal_in(choice, allowed) for choice in choices
                ):
                    _add_error(
                        errors,
                        "kind_form_invalid",
                        f"{where}.when['{param}'] contains an invalid value",
                    )
            elif not isinstance(choices, dict):
                _add_error(
                    errors,
                    "kind_form_invalid",
                    f"{where}.by['{param}'] must be a mapping",
                )
            else:
                for choice, coefficient in choices.items():
                    if not _literal_in(choice, allowed):
                        _add_error(
                            errors,
                            "kind_form_invalid",
                            f"{where}.by['{param}'] has invalid value "
                            f"{choice!r}",
                        )
                    _validate_cost_scalar(
                        coefficient,
                        f"{where}.by['{param}'][{choice!r}]",
                        errors,
                        regular_rule="kind_form_invalid",
                    )


def _validate_dependencies(
    value: Any,
    definitions: dict[str, dict[str, Any]],
    where: str,
    errors: list[str],
) -> None:
    if isinstance(value, list):
        if not _is_string_list(value):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} dependencies must contain non-empty strings",
            )
        return
    if not isinstance(value, dict) or set(value) != {"by"}:
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} dependencies must be a list or a 'by' selector",
        )
        return
    selectors = value.get("by")
    if not isinstance(selectors, dict) or not selectors:
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} dependencies.by must be a non-empty mapping",
        )
        return
    for param, branches in selectors.items():
        definition = definitions.get(param, {})
        param_type = definition.get("type")
        allowed = (
            definition.get("values", [])
            if param_type == "enum"
            else [False, True]
        )
        if param_type not in {"enum", "boolean"}:
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} dependencies.by references non-enum param "
                f"{param!r}",
            )
        if not isinstance(branches, dict):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} dependencies.by['{param}'] must be a mapping",
            )
            continue
        for choice, dependencies in branches.items():
            if not _literal_in(choice, allowed):
                _add_error(
                    errors,
                    "kind_form_invalid",
                    f"{where} dependencies.by['{param}'] has invalid "
                    f"value {choice!r}",
                )
            if not _is_string_list(dependencies):
                _add_error(
                    errors,
                    "kind_form_invalid",
                    f"{where} dependency branch values must be lists of "
                    "non-empty strings",
                )


def _validate_revenue(
    value: Any,
    where: str,
    errors: list[str],
    *,
    parametric: bool,
    definitions: Optional[dict[str, dict[str, Any]]] = None,
    numeric_refs: Optional[set[str]] = None,
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _add_error(
            errors, "revenue_invalid", f"{where} revenue must be a list"
        )
        return
    definitions = definitions or {}
    numeric_refs = numeric_refs or set()
    for index, stream in enumerate(value):
        rwhere = f"{where} revenue[{index}]"
        if not isinstance(stream, dict):
            _add_error(
                errors,
                "revenue_invalid",
                f"{rwhere} must be a mapping",
            )
            continue
        for key in ("stream", "family", "unit"):
            if not _is_string(stream.get(key), nonempty=True):
                _add_error(
                    errors,
                    "revenue_invalid",
                    f"{rwhere} missing '{key}'",
                )
        if "price_usd" not in stream:
            _add_error(
                errors,
                "revenue_invalid",
                f"{rwhere} missing 'price_usd'",
            )
        elif parametric:
            _validate_form(
                stream["price_usd"],
                definitions,
                numeric_refs,
                f"{rwhere}.price_usd",
                errors,
            )
        else:
            _validate_cost_scalar(
                stream["price_usd"],
                f"{rwhere}.price_usd",
                errors,
                regular_rule="revenue_invalid",
            )
        volume = stream.get("volume_per_year")
        if not isinstance(volume, list) or not volume:
            _add_error(
                errors,
                "revenue_invalid",
                f"{rwhere}.volume_per_year must be a non-empty list",
            )
        else:
            for year, amount in enumerate(volume):
                if parametric:
                    _validate_form(
                        amount,
                        definitions,
                        numeric_refs,
                        f"{rwhere}.volume_per_year[{year}]",
                        errors,
                    )
                else:
                    _validate_cost_scalar(
                        amount,
                        f"{rwhere}.volume_per_year[{year}]",
                        errors,
                        regular_rule="revenue_invalid",
                    )
        starts = stream.get("starts", "completion")
        if starts not in {"completion", "start"}:
            _add_error(
                errors,
                "revenue_invalid",
                f"{rwhere}.starts must be 'completion' or 'start'",
            )
        ramp = stream.get("ramp_months")
        if ramp is not None and (not _is_number(ramp) or ramp < 0):
            _add_error(
                errors,
                "revenue_invalid",
                f"{rwhere}.ramp_months must be a non-negative number or null",
            )
        provenance = stream.get("provenance")
        if provenance is not None and not _is_string_list(provenance):
            _add_error(
                errors,
                "revenue_invalid",
                f"{rwhere}.provenance must be a list of non-empty strings",
            )


def _validate_kind_resourcing(
    value: Any,
    definitions: dict[str, dict[str, Any]],
    numeric_refs: set[str],
    where: str,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} missing 'resourcing' mapping",
        )
        return
    costed = False
    for map_key in ("fte_months", "units"):
        entries = value.get(map_key)
        if entries is None:
            continue
        if not isinstance(entries, dict):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} resourcing.{map_key} must be a mapping",
            )
            continue
        costed = costed or bool(entries)
        for name, form in entries.items():
            if not _is_string(name, nonempty=True):
                _add_error(
                    errors,
                    "kind_form_invalid",
                    f"{where} resourcing.{map_key} keys must be strings",
                )
            _validate_form(
                form,
                definitions,
                numeric_refs,
                f"{where} resourcing.{map_key}['{name}']",
                errors,
            )
    for key in (
        "contract_usd",
        "recurring_usd_per_year",
        "amount_usd",
        "non_personnel_usd_per_year",
    ):
        if key in value and value[key] is not None:
            costed = True
            _validate_form(
                value[key],
                definitions,
                numeric_refs,
                f"{where} resourcing.{key}",
                errors,
            )
    if "overhead_included" in value and not isinstance(
        value["overhead_included"], bool
    ):
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} resourcing.overhead_included must be a boolean",
        )
    roster = value.get("roster")
    if roster is not None:
        costed = True
        # Roster fte/months are decisions, not FORMs or estimates.
        _validate_resourcing({"roster": roster}, where, errors)
    non_personnel = value.get("non_personnel")
    if non_personnel is not None:
        costed = costed or bool(non_personnel)
        # Itemized lines are concrete source-model facts, not FORMs.
        _validate_non_personnel(non_personnel, where, errors)
    if (
        value.get("non_personnel_usd_per_year") is not None
        and isinstance(non_personnel, list)
        and non_personnel
    ):
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} cannot mix 'non_personnel_usd_per_year' with "
            "itemized 'non_personnel'",
        )
    if not costed:
        _add_error(
            errors,
            "kind_form_invalid",
            f"{where} resourcing must contain a costed field",
        )


def _validate_kinds(
    data: dict[str, Any], errors: list[str]
) -> dict[str, tuple[dict[str, dict[str, Any]], set[str]]]:
    raw_kinds = data.get("kinds")
    if raw_kinds is None:
        return {}
    if not isinstance(raw_kinds, dict):
        _add_error(errors, "kind_form_invalid", "'kinds' must be a mapping")
        return {}
    result: dict[str, tuple[dict[str, dict[str, Any]], set[str]]] = {}
    for kind_id, kind in raw_kinds.items():
        where = f"kinds['{kind_id}']"
        if not _is_string(kind_id, nonempty=True) or not _ITEM_ID_RE.match(
            kind_id
        ):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} id must match [a-z0-9-]+",
            )
        if not isinstance(kind, dict):
            _add_error(
                errors, "kind_form_invalid", f"{where} must be a mapping"
            )
            continue
        for key in ("title", "doc", "type", "what", "evidence"):
            if key in kind and not _is_string(kind[key], nonempty=True):
                _add_error(
                    errors,
                    "kind_form_invalid",
                    f"{where} '{key}' must be a non-empty string",
                )
        definitions = _validate_param_definitions(
            kind.get("params"), where, errors
        )
        numeric_refs = _validate_derived(
            kind.get("derived"), definitions, where, errors
        )
        _validate_kind_resourcing(
            kind.get("resourcing"),
            definitions,
            numeric_refs,
            where,
            errors,
        )
        if kind.get("duration_months") is not None:
            _validate_form(
                kind["duration_months"],
                definitions,
                numeric_refs,
                f"{where} duration_months",
                errors,
            )
        _validate_dependencies(
            kind.get("dependencies", []), definitions, where, errors
        )
        _validate_revenue(
            kind.get("revenue"),
            where,
            errors,
            parametric=True,
            definitions=definitions,
            numeric_refs=numeric_refs,
        )
        if not _is_optional_string(kind.get("title_template")):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} title_template must be a string or null",
            )
        status = kind.get("status", "planned")
        if status not in VALID_ITEM_STATUSES:
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} invalid status {status!r}",
            )
        provenance = kind.get("provenance")
        if provenance is not None and not _is_string_list(provenance):
            _add_error(
                errors,
                "kind_form_invalid",
                f"{where} provenance must be a list of strings",
            )
        result[str(kind_id)] = (definitions, numeric_refs)
    return result


def _validate_kind_presets(
    value: Any,
    kinds: dict[str, tuple[dict[str, dict[str, Any]], set[str]]],
    errors: list[str],
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        _add_error(
            errors,
            "kind_param_invalid",
            "'kind_presets' must be a mapping",
        )
        return
    for name, preset in value.items():
        where = f"kind_presets['{name}']"
        if not _is_string(name, nonempty=True) or not isinstance(preset, dict):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{where} must have a string name and mapping value",
            )
            continue
        kind_id = preset.get("kind")
        if kind_id not in kinds:
            _add_error(
                errors,
                "kind_unknown",
                f"{where} references unknown kind {kind_id!r}",
            )
            continue
        if not _is_string(preset.get("title"), nonempty=True):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{where} missing 'title'",
            )
        _validate_param_values(
            preset.get("params", {}), kinds[kind_id][0], where, errors
        )


def validate_menu(data: Any) -> list[str]:
    """Validate a raw ``menu.yaml`` dict. Empty list == valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["menu must be a mapping/dict"]
    _validate_schema_key(data, ALLOWED_MENU_SCHEMAS, errors, "menu_invalid")
    _validate_menu_schema_version(data, errors)

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
                _validate_cost_scalar(
                    price,
                    f"{where} 'usd_per_unit'",
                    errors,
                    regular_rule="menu_invalid",
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

    kinds = _validate_kinds(data, errors)
    _validate_kind_presets(data.get("kind_presets"), kinds, errors)

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
        kind_id = item.get("kind")
        kind_backed = kind_id is not None
        kind_definition: Optional[
            tuple[dict[str, dict[str, Any]], set[str]]
        ] = None
        if kind_backed:
            if not _is_string(kind_id, nonempty=True) or kind_id not in kinds:
                _add_error(
                    errors,
                    "kind_unknown",
                    f"{label} references unknown kind {kind_id!r}",
                )
            else:
                kind_definition = kinds[kind_id]
                _validate_param_values(
                    item.get("params", {}),
                    kind_definition[0],
                    label,
                    errors,
                )
        elif "params" in item:
            _add_error(
                errors,
                "kind_param_invalid",
                f"{label} has params but no kind",
            )
        required_text: tuple[str, ...] = ("what", "evidence")
        if not kind_backed:
            required_text = ("type", "title", *required_text)
        for key in required_text:
            if not _is_string(item.get(key), nonempty=True):
                errors.append(f"{label} missing '{key}'")
        if kind_backed:
            for key in ("type", "title"):
                if key in item and not _is_string(
                    item.get(key), nonempty=True
                ):
                    errors.append(f"{label} '{key}' must be a string")
        status = item.get("status")
        if not _is_string(status) or status not in VALID_ITEM_STATUSES:
            errors.append(
                f"{label} invalid status {status!r} "
                f"(allowed: {sorted(VALID_ITEM_STATUSES)})"
            )
        duration = item.get("duration_months")
        if not _is_int_or_none(duration) or (
            isinstance(duration, int)
            and not isinstance(duration, bool)
            and duration < 0
        ):
            errors.append(
                f"{label} 'duration_months' must be a non-negative "
                "integer or null"
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
        if not kind_backed or "resourcing" in item:
            _validate_resourcing(item.get("resourcing"), label, errors)
        _validate_revenue(item.get("revenue"), label, errors, parametric=False)
    return errors


def validate_rates(data: Any) -> list[str]:
    """Validate a raw ``rates.yaml`` dict. Empty list == valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["rates must be a mapping/dict"]
    _validate_schema_key(data, ALLOWED_RATES_SCHEMAS, errors, "rates_invalid")
    _validate_rates_schema_version(data, errors)

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
        _validate_cost_scalar(
            loaded,
            f"{label} 'loaded_usd'",
            errors,
            regular_rule="rates_invalid",
            positive=True,
        )
        base = role.get("base_usd")
        if base is not None:
            _validate_cost_scalar(
                base,
                f"{label} 'base_usd'",
                errors,
                regular_rule="rates_invalid",
            )
        capacity = role.get("capacity_fte")
        if capacity is not None and (not _is_number(capacity) or capacity < 0):
            errors.append(
                f"{label} 'capacity_fte' must be a non-negative number "
                "or null"
            )
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
                    _validate_cost_scalar(
                        amount,
                        f"{cwhere} 'amount_usd'",
                        errors,
                        regular_rule="rates_invalid",
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
                percentile = benchmark.get("percentile")
                if not _is_number_or_none(percentile):
                    errors.append(
                        f"{label} benchmark.percentile must be a number "
                        "or null"
                    )
                benchmark_value = benchmark.get("value_usd")
                if benchmark_value is not None:
                    _validate_cost_scalar(
                        benchmark_value,
                        f"{label} benchmark.value_usd",
                        errors,
                        regular_rule="rates_invalid",
                    )
        provenance = role.get("provenance")
        if provenance is not None and not _is_string_list(provenance):
            errors.append(
                f"{label} 'provenance' must be a list of non-empty strings"
            )
    return errors


def _selection_menu_context(
    menu: Any,
) -> tuple[dict[str, dict[str, dict[str, Any]]], set[str]]:
    if menu is None:
        return {}, set()
    if hasattr(menu, "menu_data"):
        menu = menu.menu_data
    elif isinstance(menu, Menu):
        menu = menu.raw
    if not isinstance(menu, dict):
        return {}, set()
    item_ids = {
        str(item.get("id"))
        for item in menu.get("items", [])
        if isinstance(item, dict) and _is_string(item.get("id"), nonempty=True)
    }
    result: dict[str, dict[str, dict[str, Any]]] = {}
    raw_kinds = menu.get("kinds")
    if isinstance(raw_kinds, dict):
        for kind_id, kind in raw_kinds.items():
            if not isinstance(kind, dict):
                continue
            scratch: list[str] = []
            result[str(kind_id)] = _validate_param_definitions(
                kind.get("params"), f"kinds['{kind_id}']", scratch
            )
    return result, item_ids


def validate_selection(data: Any, menu: Any = None) -> list[str]:
    """Validate a raw ``selection.yaml`` dict. Empty list == valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["selection must be a mapping/dict"]
    _validate_schema_key(
        data, ALLOWED_SELECTION_SCHEMAS, errors, "selection_invalid"
    )
    _validate_selection_schema_version(data, errors)

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
    horizon = data.get("horizon_months", window)
    if (
        not isinstance(horizon, int)
        or isinstance(horizon, bool)
        or horizon <= 0
        or not _is_number(horizon)
    ):
        errors.append("'horizon_months' must be an integer > 0")

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
    kind_definitions, menu_item_ids = _selection_menu_context(menu)
    check_kind_refs = menu is not None
    seen_instance_ids: set[str] = set()
    for i, line in enumerate(lines):
        where = f"selections[{i}]"
        if not isinstance(line, dict):
            errors.append(f"{where} must be a mapping")
            continue
        has_item = "item" in line and line.get("item") is not None
        has_instance = "instance" in line and line.get("instance") is not None
        if has_item == has_instance:
            detail = "missing 'item'" if not has_item else "both are present"
            _add_error(
                errors,
                "selection_invalid",
                f"{where} must contain exactly one of 'item' or "
                f"'instance' ({detail})",
            )
        elif has_item and not _is_string(line.get("item"), nonempty=True):
            errors.append(f"{where} missing 'item'")
        if not _is_number(line.get("fraction")):
            errors.append(
                f"{where} ('{line.get('item')}') 'fraction' must be "
                f"a number"
            )
        start = line.get("start_month", 0)
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or start < 0
            or not _is_number(start)
        ):
            errors.append(f"{where} 'start_month' must be an integer >= 0")
        if not _is_optional_string(line.get("note")):
            errors.append(f"{where} 'note' must be a string or null")
        if not has_instance:
            continue
        instance = line.get("instance")
        if not isinstance(instance, dict):
            _add_error(
                errors,
                "selection_invalid",
                f"{where} 'instance' must be a mapping",
            )
            continue
        iwhere = f"{where} instance"
        instance_id = instance.get("id")
        if not _is_string(instance_id, nonempty=True) or not _ITEM_ID_RE.match(
            instance_id
        ):
            _add_error(
                errors,
                "instance_id_collision",
                f"{iwhere} id must match [a-z0-9-]+",
            )
        elif instance_id in seen_instance_ids or instance_id in menu_item_ids:
            _add_error(
                errors,
                "instance_id_collision",
                f"{iwhere} id '{instance_id}' repeats or collides with a "
                "menu item id",
            )
        else:
            seen_instance_ids.add(instance_id)
        kind_id = instance.get("kind")
        if not _is_string(kind_id, nonempty=True):
            _add_error(
                errors,
                "kind_unknown",
                f"{iwhere} missing 'kind'",
            )
        elif check_kind_refs and kind_id not in kind_definitions:
            _add_error(
                errors,
                "kind_unknown",
                f"{iwhere} references unknown kind {kind_id!r}",
            )
        elif kind_id in kind_definitions:
            _validate_param_values(
                instance.get("params", {}),
                kind_definitions[kind_id],
                iwhere,
                errors,
            )
        elif not isinstance(instance.get("params", {}), dict):
            _add_error(
                errors,
                "kind_param_invalid",
                f"{iwhere} 'params' must be a mapping",
            )
        for text_key in ("title", "type"):
            if not _is_optional_string(instance.get(text_key)):
                errors.append(
                    f"{iwhere} '{text_key}' must be a string or null"
                )
        if "resourcing" in instance:
            _validate_resourcing(instance.get("resourcing"), iwhere, errors)
        duration = instance.get("duration_months")
        if not _is_int_or_none(duration) or (
            isinstance(duration, int)
            and not isinstance(duration, bool)
            and duration < 0
        ):
            errors.append(
                f"{iwhere} 'duration_months' must be a non-negative "
                "integer or null"
            )
        dependencies = instance.get("dependencies")
        if dependencies is not None and not _is_string_list(dependencies):
            errors.append(
                f"{iwhere} 'dependencies' must be a list of non-empty "
                "strings"
            )
        provenance = instance.get("provenance")
        if provenance is not None and not _is_string_list(provenance):
            errors.append(
                f"{iwhere} 'provenance' must be a list of non-empty strings"
            )
        _validate_revenue(
            instance.get("revenue"), iwhere, errors, parametric=False
        )
    if not _is_optional_string(data.get("notes")):
        errors.append("'notes' must be a string or null")
    return errors
