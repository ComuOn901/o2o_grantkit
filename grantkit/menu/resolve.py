"""Resolve explicit and parametric menu items to concrete inputs.

This module contains the deliberately small expression language used by
``grantkit-menu/v1``.  Resolution is pure: it applies kind defaults, derives
parameters in declaration order, evaluates FORM values, and overlays any
explicit item or inline-instance fields.  The costing engine therefore only
has to consume concrete resourcing, duration, dependencies, and revenue.

FORM arithmetic uses Python floats, as does the rest of the budget engine.
No rounding happens here.  Estimate objects contribute their ``central``
value and are also copied into a flat, path-keyed metadata map for future
uncertainty sampling.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional

from . import schema as schema_module
from .schema import Resourcing, RosterLine

EstimateMap = dict[str, dict[str, Any]]

_NUMBER_TYPES = (int, float)
_FORM_KEYS = {"const", "per", "by", "when"}
_RESOURCE_MAP_FIELDS = ("fte_months", "units")
_RESOURCE_SCALAR_FIELDS = (
    "contract_usd",
    "recurring_usd_per_year",
    "amount_usd",
    "non_personnel_usd_per_year",
)
_ESTIMATE_KEYS = ("central", "low", "high", "basis", "source")
_TEMPLATE_FIELD_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _is_number(value: Any) -> bool:
    return isinstance(value, _NUMBER_TYPES) and not isinstance(value, bool)


def _finite_float(value: Any, *, where: str) -> float:
    if not _is_number(value):
        raise ValueError(f"{where or 'value'} must be a number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{where or 'value'} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{where or 'value'} must be finite")
    return result


def _path_part(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _join_path(path: str, part: Any) -> str:
    text = _path_part(part)
    return f"{path}.{text}" if path else text


def _estimate_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    """Copy estimate metadata in one stable key order."""
    return {key: value[key] for key in _ESTIMATE_KEYS if key in value}


def _record_estimate(
    value: Mapping[str, Any],
    estimates: Optional[MutableMapping[str, Any]],
    path: str,
) -> None:
    if estimates is None:
        return
    key = path or "value"
    estimates.setdefault(key, _estimate_metadata(value))


def _collect_estimates(
    value: Any,
    estimates: Optional[MutableMapping[str, Any]],
    path: str,
) -> None:
    """Collect every estimate below ``value``, including inactive forms."""
    if estimates is None:
        return
    if isinstance(value, Mapping):
        if "central" in value:
            _record_estimate(value, estimates, path)
            return
        for key, entry in value.items():
            _collect_estimates(entry, estimates, _join_path(path, key))
    elif isinstance(value, list):
        for index, entry in enumerate(value):
            _collect_estimates(entry, estimates, _join_path(path, index))


def _strict_equal(left: Any, right: Any) -> bool:
    """Compare enum values without Python's ``True == 1`` coercion."""
    if isinstance(left, bool) or isinstance(right, bool):
        return (
            isinstance(left, bool)
            and isinstance(right, bool)
            and (left is right)
        )
    if _is_number(left) or _is_number(right):
        return _is_number(left) and _is_number(right) and left == right
    return type(left) is type(right) and left == right


def _choice_for(value: Any, choices: Mapping[Any, Any]) -> tuple[Any, Any]:
    for choice, result in choices.items():
        if _strict_equal(value, choice):
            return choice, result
    return None, None


def evaluate_form(
    form: Any,
    params: Mapping[str, Any],
    estimates: Optional[MutableMapping[str, Any]] = None,
    path: str = "",
) -> float:
    """Evaluate one FORM (or a recursively summed list of FORMs).

    A FORM is a number, an estimate object, or a mapping containing any of
    ``const``, ``per``, ``by``, and ``when``.  Lists are summed recursively.
    Mapping iteration order is preserved for deterministic float arithmetic.

    ``when`` comparisons are type-strict for booleans and enums.  A missing
    ``by`` entry contributes zero.  Invalid inputs raise :class:`ValueError`;
    document validators normally report those errors before resolution.
    """
    _collect_estimates(form, estimates, path)

    if _is_number(form):
        return _finite_float(form, where=path)

    if isinstance(form, list):
        total = 0.0
        for index, entry in enumerate(form):
            total += evaluate_form(
                entry,
                params,
                estimates,
                _join_path(path, index),
            )
        if not math.isfinite(total):
            raise ValueError(f"{path or 'form'} produced a non-finite value")
        return total

    if not isinstance(form, Mapping):
        raise ValueError(f"{path or 'form'} must be a FORM")

    if "central" in form:
        try:
            return float(schema_module.as_number(form))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"{path or 'estimate'} is invalid: {exc}"
            ) from exc

    unknown = set(form) - _FORM_KEYS
    if unknown:
        joined = ", ".join(sorted(str(key) for key in unknown))
        raise ValueError(f"{path or 'form'} has unknown FORM keys: {joined}")

    conditions = form.get("when")
    if conditions is not None:
        if not isinstance(conditions, Mapping):
            raise ValueError(f"{_join_path(path, 'when')} must be a mapping")
        for name, accepted in conditions.items():
            if name not in params:
                raise ValueError(
                    f"{_join_path(path, 'when')} references unknown "
                    f"parameter '{name}'"
                )
            if not isinstance(accepted, list):
                raise ValueError(
                    f"{_join_path(_join_path(path, 'when'), name)} "
                    "must be a list"
                )
            if not any(
                _strict_equal(params[name], candidate)
                for candidate in accepted
            ):
                return 0.0

    total = 0.0
    if "const" in form:
        total += evaluate_form(
            form["const"],
            params,
            estimates,
            _join_path(path, "const"),
        )

    per = form.get("per")
    if per is not None:
        if not isinstance(per, Mapping):
            raise ValueError(f"{_join_path(path, 'per')} must be a mapping")
        for name, coefficient in per.items():
            if name not in params:
                raise ValueError(
                    f"{_join_path(path, 'per')} references unknown "
                    f"parameter '{name}'"
                )
            parameter = _finite_float(
                params[name], where=_join_path("params", name)
            )
            coefficient_value = evaluate_form(
                coefficient,
                params,
                estimates,
                _join_path(_join_path(path, "per"), name),
            )
            total += coefficient_value * parameter

    by = form.get("by")
    if by is not None:
        if not isinstance(by, Mapping):
            raise ValueError(f"{_join_path(path, 'by')} must be a mapping")
        for name, choices in by.items():
            if name not in params:
                raise ValueError(
                    f"{_join_path(path, 'by')} references unknown "
                    f"parameter '{name}'"
                )
            if not isinstance(choices, Mapping):
                raise ValueError(
                    f"{_join_path(_join_path(path, 'by'), name)} "
                    "must be a mapping"
                )
            choice, selected = _choice_for(params[name], choices)
            if choice is not None:
                total += evaluate_form(
                    selected,
                    params,
                    estimates,
                    _join_path(
                        _join_path(_join_path(path, "by"), name),
                        choice,
                    ),
                )

    if not math.isfinite(total):
        raise ValueError(f"{path or 'form'} produced a non-finite value")
    return total


def _sorted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in sorted(value)}


def _roster_to_dict(entry: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": str(_field(entry, "role", default="")),
        "fte": float(_field(entry, "fte", default=0.0)),
    }
    months = _field(entry, "months", default=None)
    if months is not None:
        result["months"] = float(months)
    return result


def _resourcing_to_dict(resourcing: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "fte_months": _sorted_mapping(
            _field(resourcing, "fte_months", default={})
        ),
        "units": _sorted_mapping(_field(resourcing, "units", default={})),
        "contract_usd": _field(resourcing, "contract_usd", default=None),
        "recurring_usd_per_year": _field(
            resourcing, "recurring_usd_per_year", default=None
        ),
        "amount_usd": _field(resourcing, "amount_usd", default=None),
        "overhead_included": bool(
            _field(resourcing, "overhead_included", default=False)
        ),
    }
    roster = _field(resourcing, "roster", default=[])
    result["roster"] = [_roster_to_dict(entry) for entry in roster]
    result["non_personnel_usd_per_year"] = _field(
        resourcing,
        "non_personnel_usd_per_year",
        default=None,
    )
    return result


@dataclass
class ResolvedRevenueStream:
    """One revenue stream with all price and volume FORMs resolved."""

    stream: str
    family: str = ""
    unit: str = ""
    price_usd: float = 0.0
    volume_per_year: list[float] = field(default_factory=list)
    starts: str = "completion"
    ramp_months: Optional[float] = None
    provenance: list[str] = field(default_factory=list)
    estimates: EstimateMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream": self.stream,
            "family": self.family,
            "unit": self.unit,
            "price_usd": self.price_usd,
            "volume_per_year": list(self.volume_per_year),
            "starts": self.starts,
            "ramp_months": self.ramp_months,
            "provenance": list(self.provenance),
            "estimates": {
                path: dict(self.estimates[path])
                for path in sorted(self.estimates)
            },
        }


@dataclass
class ResolvedItem:
    """A concrete item ready for costing, phasing, and revenue projection."""

    id: str
    type: str
    title: str
    what: str
    evidence: str
    status: str
    resourcing: Resourcing
    duration_months: float = 1.0
    dependencies: list[str] = field(default_factory=list)
    revenue: list[ResolvedRevenueStream] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    revenue_unlock: Optional[str] = None
    kind: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, float] = field(default_factory=dict)
    estimates: EstimateMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "what": self.what,
            "evidence": self.evidence,
            "status": self.status,
            "resourcing": _resourcing_to_dict(self.resourcing),
            "duration_months": self.duration_months,
            "dependencies": list(self.dependencies),
            "revenue": [entry.to_dict() for entry in self.revenue],
            "provenance": list(self.provenance),
            "revenue_unlock": self.revenue_unlock,
            "kind": self.kind,
            "params": dict(self.params),
            "derived": dict(self.derived),
            "estimates": {
                path: dict(self.estimates[path])
                for path in sorted(self.estimates)
            },
        }


def _field(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _raw(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raw = getattr(value, "raw", None)
    return dict(raw) if isinstance(raw, Mapping) else {}


def _kind_lookup(kinds: Any) -> dict[str, Any]:
    if isinstance(kinds, Mapping):
        return {str(name): kind for name, kind in kinds.items()}
    result: dict[str, Any] = {}
    for kind in kinds or []:
        kind_id = str(_field(kind, "id", default=""))
        if kind_id:
            result[kind_id] = kind
    return result


def _stable_union(*values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for entries in values:
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, str) and entry not in seen:
                seen.add(entry)
                result.append(entry)
    return result


def _definition_default(definition: Any) -> Any:
    return _field(definition, "default", default=None)


def _resolve_operand(
    operand: Any,
    params: Mapping[str, Any],
    estimates: MutableMapping[str, Any],
    path: str,
) -> float:
    if isinstance(operand, str):
        if operand not in params:
            raise ValueError(f"{path} references unknown value '{operand}'")
        return _finite_float(params[operand], where=path)
    return evaluate_form(operand, params, estimates, path)


def _resolve_derived(
    definitions: Mapping[str, Any],
    params: dict[str, Any],
    estimates: MutableMapping[str, Any],
    path: str,
) -> dict[str, float]:
    derived: dict[str, float] = {}
    for name, definition in definitions.items():
        raw_definition = _raw(definition) or definition
        if not isinstance(raw_definition, Mapping):
            raise ValueError(f"{_join_path(path, name)} must be a mapping")
        operations = [
            operation
            for operation in ("product", "sum")
            if operation in raw_definition
        ]
        if len(operations) != 1:
            raise ValueError(
                f"{_join_path(path, name)} must contain product or sum"
            )
        operation = operations[0]
        operands = raw_definition[operation]
        if not isinstance(operands, list):
            raise ValueError(
                f"{_join_path(_join_path(path, name), operation)} "
                "must be a list"
            )
        total = 1.0 if operation == "product" else 0.0
        available = {**params, **derived}
        for index, operand in enumerate(operands):
            value = _resolve_operand(
                operand,
                available,
                estimates,
                _join_path(
                    _join_path(_join_path(path, name), operation), index
                ),
            )
            total = total * value if operation == "product" else total + value
        if not math.isfinite(total):
            raise ValueError(
                f"{_join_path(path, name)} produced a non-finite value"
            )
        derived[str(name)] = total
    params.update(derived)
    return derived


def _resolve_resource_mapping(
    value: Any,
    params: Mapping[str, Any],
    estimates: MutableMapping[str, Any],
    path: str,
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(name): evaluate_form(
            form,
            params,
            estimates,
            _join_path(path, name),
        )
        for name, form in value.items()
    }


def _resolve_roster(value: Any, path: str) -> list[RosterLine]:
    if not isinstance(value, list):
        return []
    result: list[RosterLine] = []
    for index, entry in enumerate(value):
        role = str(_field(entry, "role", default=""))
        fte = _finite_float(
            _field(entry, "fte", default=None),
            where=_join_path(_join_path(path, index), "fte"),
        )
        months_value = _field(entry, "months", default=None)
        months = (
            None
            if months_value is None
            else _finite_float(
                months_value,
                where=_join_path(_join_path(path, index), "months"),
            )
        )
        result.append(RosterLine(role=role, fte=fte, months=months))
    return result


def _resolve_resourcing(
    value: Any,
    params: Mapping[str, Any],
    estimates: MutableMapping[str, Any],
    path: str,
) -> dict[str, Any]:
    raw_value = _raw(value)
    result: dict[str, Any] = {
        "fte_months": {},
        "units": {},
        "contract_usd": None,
        "recurring_usd_per_year": None,
        "amount_usd": None,
        "overhead_included": False,
        "roster": [],
        "non_personnel_usd_per_year": None,
    }
    for name in _RESOURCE_MAP_FIELDS:
        if name in raw_value:
            result[name] = _resolve_resource_mapping(
                raw_value[name],
                params,
                estimates,
                _join_path(path, name),
            )
    for name in _RESOURCE_SCALAR_FIELDS:
        if name in raw_value:
            raw_scalar = raw_value[name]
            result[name] = (
                None
                if raw_scalar is None
                else evaluate_form(
                    raw_scalar,
                    params,
                    estimates,
                    _join_path(path, name),
                )
            )
    if "overhead_included" in raw_value:
        result["overhead_included"] = bool(raw_value["overhead_included"])
    if "roster" in raw_value:
        result["roster"] = _resolve_roster(
            raw_value["roster"], _join_path(path, "roster")
        )
    return result


def _merge_resourcing(
    base: dict[str, Any],
    override: dict[str, Any],
    override_raw: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(base)
    for name in _RESOURCE_MAP_FIELDS:
        merged = dict(base.get(name, {}))
        if name in override_raw:
            merged.update(override.get(name, {}))
        result[name] = merged
    for name in (*_RESOURCE_SCALAR_FIELDS, "overhead_included", "roster"):
        if name in override_raw:
            result[name] = override.get(name)
    return result


def _build_resourcing(values: Mapping[str, Any]) -> Resourcing:
    return Resourcing(
        fte_months=dict(values.get("fte_months", {})),
        units=dict(values.get("units", {})),
        contract_usd=values.get("contract_usd"),
        recurring_usd_per_year=values.get("recurring_usd_per_year"),
        amount_usd=values.get("amount_usd"),
        overhead_included=bool(values.get("overhead_included", False)),
        roster=list(values.get("roster", [])),
        non_personnel_usd_per_year=values.get("non_personnel_usd_per_year"),
    )


def _resolve_dependencies(value: Any, params: Mapping[str, Any]) -> list[str]:
    raw_value = _raw(value) or value
    if isinstance(raw_value, list):
        return [entry for entry in raw_value if isinstance(entry, str)]
    if not isinstance(raw_value, Mapping):
        return []
    by = raw_value.get("by")
    if not isinstance(by, Mapping):
        return []
    result: list[str] = []
    for name, choices in by.items():
        if name not in params or not isinstance(choices, Mapping):
            continue
        _, selected = _choice_for(params[name], choices)
        if isinstance(selected, list):
            result = _stable_union(result, selected)
    return result


def _stream_raw(stream: Any) -> dict[str, Any]:
    raw = _raw(stream)
    if raw:
        return raw
    return {
        "stream": _field(stream, "stream", default=""),
        "family": _field(stream, "family", default=""),
        "unit": _field(stream, "unit", default=""),
        "price_usd": _field(stream, "price_usd", default=0.0),
        "volume_per_year": _field(stream, "volume_per_year", default=[]),
        "starts": _field(stream, "starts", default="completion"),
        "ramp_months": _field(stream, "ramp_months", default=None),
        "provenance": _field(stream, "provenance", default=[]),
    }


def _resolve_revenue(
    streams: Any,
    params: Mapping[str, Any],
    estimates: MutableMapping[str, Any],
    path: str,
) -> list[ResolvedRevenueStream]:
    if not isinstance(streams, list):
        return []
    result: list[ResolvedRevenueStream] = []
    for index, stream in enumerate(streams):
        raw_stream = _stream_raw(stream)
        stream_path = _join_path(path, index)
        local_estimates: EstimateMap = {}
        price = evaluate_form(
            raw_stream.get("price_usd", 0.0),
            params,
            local_estimates,
            _join_path(stream_path, "price_usd"),
        )
        raw_volume = raw_stream.get("volume_per_year", [])
        if not isinstance(raw_volume, list) or not raw_volume:
            raise ValueError(
                f"{_join_path(stream_path, 'volume_per_year')} must be "
                "a non-empty list"
            )
        # The outer list is the time series.  A nested list is the summed
        # list-of-forms extension for that one year, not another time axis.
        volume = [
            evaluate_form(
                entry,
                params,
                local_estimates,
                _join_path(_join_path(stream_path, "volume_per_year"), year),
            )
            for year, entry in enumerate(raw_volume)
        ]
        if price < 0 or any(entry < 0 for entry in volume):
            raise ValueError(f"{stream_path} revenue must be non-negative")
        ramp_value = raw_stream.get("ramp_months")
        ramp = (
            None
            if ramp_value is None
            else _finite_float(
                ramp_value, where=_join_path(stream_path, "ramp_months")
            )
        )
        if ramp is not None and ramp < 0:
            raise ValueError(
                f"{_join_path(stream_path, 'ramp_months')} must be "
                "non-negative"
            )
        for estimate_path, metadata in local_estimates.items():
            estimates.setdefault(estimate_path, metadata)
        result.append(
            ResolvedRevenueStream(
                stream=str(raw_stream.get("stream", "")),
                family=str(raw_stream.get("family", "")),
                unit=str(raw_stream.get("unit", "")),
                price_usd=price,
                volume_per_year=volume,
                starts=str(raw_stream.get("starts", "completion")),
                ramp_months=ramp,
                provenance=[
                    entry
                    for entry in raw_stream.get("provenance", [])
                    if isinstance(entry, str)
                ],
                estimates=local_estimates,
            )
        )
    return result


def _template_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if _is_number(value):
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else repr(numeric)
    return str(value)


def _render_title(template: str, params: Mapping[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError(
                f"title_template references unknown parameter '{name}'"
            )
        return _template_value(params[name])

    return _TEMPLATE_FIELD_RE.sub(replace, template)


def _metadata_value(
    explicit: Any,
    kind: Any,
    name: str,
    *,
    default: Any,
) -> Any:
    value = _field(explicit, name, default=None)
    if value not in (None, ""):
        return value
    value = _field(kind, name, default=None)
    return value if value not in (None, "") else default


def _concrete_resourcing_source(value: Any) -> dict[str, Any]:
    """Represent a directly-constructed concrete Resourcing as raw input."""
    if value is None:
        return {}
    return _resourcing_to_dict(value)


def resolve_item(
    item_or_instance: Any,
    kinds: Any,
    path: Optional[str] = None,
) -> ResolvedItem:
    """Resolve a menu item or inline instance to concrete budget inputs."""
    item = item_or_instance
    item_raw = _raw(item)
    item_id = str(_field(item, "id", default=""))
    is_inline = (
        isinstance(item, getattr(schema_module, "InlineInstance", ()))
        or type(item).__name__ == "InlineInstance"
    )
    default_scope = "instances" if is_inline else "items"
    item_path = path or _join_path(default_scope, item_id)
    kind_id_value = _field(item, "kind", default=None)
    kind_id = str(kind_id_value) if kind_id_value else None
    kind = None
    if kind_id is not None:
        kind = _kind_lookup(kinds).get(kind_id)
        if kind is None:
            raise KeyError(f"Unknown kind '{kind_id}' for item '{item_id}'")

    estimates: EstimateMap = {}
    supplied_params = _field(item, "params", default={})
    supplied_params = (
        dict(supplied_params) if isinstance(supplied_params, Mapping) else {}
    )
    resolved_params: dict[str, Any] = {}
    derived: dict[str, float] = {}

    if kind is not None:
        kind_params = _field(kind, "params", default={})
        if isinstance(kind_params, Mapping):
            for name, definition in kind_params.items():
                resolved_params[str(name)] = _definition_default(definition)
            undeclared = set(supplied_params) - set(kind_params)
            if undeclared:
                names = ", ".join(sorted(str(name) for name in undeclared))
                raise ValueError(
                    f"Item '{item_id}' has undeclared kind parameters: "
                    f"{names}"
                )
        resolved_params.update(supplied_params)
        kind_derived = _field(kind, "derived", default={})
        if isinstance(kind_derived, Mapping):
            derived = _resolve_derived(
                kind_derived,
                resolved_params,
                estimates,
                _join_path(_join_path("kinds", kind_id), "derived"),
            )
    else:
        resolved_params.update(supplied_params)

    evaluation_params = dict(resolved_params)

    kind_resourcing_raw = (
        _raw(_field(kind, "resourcing", default={})) if kind else {}
    )
    explicit_resourcing_raw = item_raw.get("resourcing")
    if not isinstance(explicit_resourcing_raw, Mapping):
        concrete = _field(item, "resourcing", default=None)
        explicit_resourcing_raw = (
            _concrete_resourcing_source(concrete)
            if concrete is not None and not item_raw
            else {}
        )
    kind_resourcing = _resolve_resourcing(
        kind_resourcing_raw,
        evaluation_params,
        estimates,
        _join_path(_join_path("kinds", kind_id), "resourcing"),
    )
    explicit_resourcing = _resolve_resourcing(
        explicit_resourcing_raw,
        evaluation_params,
        estimates,
        _join_path(item_path, "resourcing"),
    )
    merged_resourcing = _merge_resourcing(
        kind_resourcing,
        explicit_resourcing,
        explicit_resourcing_raw,
    )

    duration_raw: Any = None
    duration_path = _join_path(item_path, "duration_months")
    if "duration_months" in item_raw:
        duration_raw = item_raw["duration_months"]
    elif kind is not None:
        duration_raw = _field(kind, "duration_months", default=None)
        duration_path = _join_path(
            _join_path("kinds", kind_id), "duration_months"
        )
    else:
        duration_raw = _field(item, "duration_months", default=None)
    duration = (
        1.0
        if duration_raw is None
        else evaluate_form(
            duration_raw,
            evaluation_params,
            estimates,
            duration_path,
        )
    )
    if not math.isfinite(duration) or duration < 0:
        raise ValueError(
            f"{duration_path} must resolve to a finite non-negative number"
        )

    kind_dependencies = (
        _resolve_dependencies(
            _field(kind, "dependencies", default=[]), evaluation_params
        )
        if kind is not None
        else []
    )
    explicit_dependencies = _field(item, "dependencies", default=[])
    dependencies = _stable_union(
        kind_dependencies,
        explicit_dependencies,
    )

    if "revenue" in item_raw:
        raw_revenue = item_raw["revenue"]
        revenue_path = _join_path(item_path, "revenue")
    elif kind is not None:
        raw_revenue = _field(kind, "revenue", default=[])
        revenue_path = _join_path(_join_path("kinds", kind_id), "revenue")
    else:
        raw_revenue = _field(item, "revenue", default=[])
        revenue_path = _join_path(item_path, "revenue")
    revenue = _resolve_revenue(
        raw_revenue,
        evaluation_params,
        estimates,
        revenue_path,
    )

    explicit_title = _field(item, "title", default=None)
    if explicit_title:
        title = str(explicit_title)
    else:
        title_template = _field(kind, "title_template", default=None)
        if title_template:
            title = _render_title(str(title_template), evaluation_params)
        else:
            title = str(_field(kind, "title", default="") or item_id)

    kind_provenance = _field(kind, "provenance", default=[])
    item_provenance = _field(item, "provenance", default=[])

    what = _metadata_value(item, kind, "what", default="")
    if not what and kind is not None:
        what = _field(kind, "doc", default="")

    explicit_type = _field(item, "type", default=None)
    resolved_type = (
        explicit_type
        if explicit_type
        else (
            kind_id
            if is_inline
            else _metadata_value(item, kind, "type", default=kind_id or "")
        )
    )
    evidence = (
        ""
        if is_inline
        else _metadata_value(item, kind, "evidence", default="")
    )
    status = (
        "planned"
        if is_inline
        else _metadata_value(item, kind, "status", default="planned")
    )

    return ResolvedItem(
        id=item_id,
        type=str(resolved_type or ""),
        title=title,
        what=str(what),
        evidence=str(evidence),
        status=str(status),
        resourcing=_build_resourcing(merged_resourcing),
        duration_months=duration,
        dependencies=dependencies,
        revenue=revenue,
        provenance=_stable_union(kind_provenance, item_provenance),
        revenue_unlock=_metadata_value(
            item, kind, "revenue_unlock", default=None
        ),
        kind=kind_id,
        params={
            key: value
            for key, value in resolved_params.items()
            if key not in derived
        },
        derived=derived,
        estimates=estimates,
    )


__all__ = [
    "ResolvedItem",
    "ResolvedRevenueStream",
    "evaluate_form",
    "resolve_item",
]
