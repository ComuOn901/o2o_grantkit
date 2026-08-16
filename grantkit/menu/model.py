"""Normalized, deterministic model bundles for external compilers.

The bundle contains only portfolio inputs and resolved menu items. It never
adds a wall-clock timestamp, an absolute path, or another environment-derived
value, so callers can serialize it reproducibly for drift checks.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .loader import Portfolio
from .resolve import resolve_item
from .schema import as_number


def _normalized_unit_costs(value: Any) -> dict[str, Any]:
    """Copy unit costs, separating an estimate from its central value."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for name in sorted(value, key=str):
        source = value[name]
        entry = deepcopy(source)
        if isinstance(source, dict) and isinstance(entry, dict):
            price = source.get("usd_per_unit")
            if isinstance(price, dict) and "central" in price:
                entry["usd_per_unit"] = as_number(price)
                entry["estimate"] = deepcopy(price)
        result[str(name)] = entry
    return result


def _normalized_kinds(value: Any) -> dict[str, Any]:
    """Copy kinds and preserve declaration-ordered derived semantics."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for kind_id in sorted(value, key=str):
        source = value[kind_id]
        kind = deepcopy(source)
        if isinstance(source, dict) and isinstance(kind, dict):
            derived = source.get("derived")
            kind["derived_order"] = (
                [str(name) for name in derived]
                if isinstance(derived, dict)
                else []
            )
        result[str(kind_id)] = kind
    return result


def _sorted_mapping(value: Any) -> dict[str, Any]:
    """Deep-copy a string-keyed mapping in deterministic key order."""
    if not isinstance(value, dict):
        return {}
    return {
        str(name): deepcopy(value[name]) for name in sorted(value, key=str)
    }


def _bundled_items(portfolio: Portfolio) -> list[dict[str, Any]]:
    raw_items = portfolio.menu_data.get("items")
    if not isinstance(raw_items, list):
        return []
    items = [entry for entry in raw_items if isinstance(entry, dict)]
    items.sort(key=lambda entry: str(entry.get("id", "")))
    return [
        {
            "raw": deepcopy(item),
            "resolved": resolve_item(
                item,
                portfolio.menu.kinds,
                path=f"menu.items.{item.get('id', '')}",
            ).to_dict(),
        }
        for item in items
    ]


def _sorted_records(value: Any, key: str) -> list[dict[str, Any]]:
    """Deep-copy mapping records sorted by one stable identifier."""
    if not isinstance(value, list):
        return []
    records = [entry for entry in value if isinstance(entry, dict)]
    records.sort(key=lambda entry: str(entry.get(key, "")))
    return [deepcopy(entry) for entry in records]


def model_bundle(portfolio: Portfolio) -> dict[str, Any]:
    """Return the deterministic ``grantkit-model/v1`` portfolio bundle.

    Raw inputs are deep-copied before normalization. Kind-derived values are
    resolved through the same pure resolver used by budget compilation, and
    no object owned by ``portfolio`` is mutated.
    """
    menu_data = portfolio.menu_data
    rates_data = portfolio.rates_data
    overheads = menu_data.get("overheads")
    return {
        "schema": "grantkit-model/v1",
        "generated_from": {
            "menu": portfolio.menu.schema,
            "rates": portfolio.rates.schema,
            "provider": portfolio.rates.provider,
            "generated": portfolio.rates.generated,
            "scenario": portfolio.rates.scenario,
        },
        "currency": portfolio.menu.currency,
        "overheads": (
            deepcopy(overheads) if isinstance(overheads, dict) else {}
        ),
        "unit_costs": _normalized_unit_costs(menu_data.get("unit_costs")),
        "kinds": _normalized_kinds(menu_data.get("kinds")),
        "kind_presets": _sorted_mapping(menu_data.get("kind_presets")),
        "items": _bundled_items(portfolio),
        "rates": {"roles": _sorted_records(rates_data.get("roles"), "role")},
        "selections": _sorted_records(portfolio.selections_data, "id"),
    }


__all__ = ["model_bundle"]
