"""Portfolio discovery and loading.

A **portfolio directory** holds the three budget-model documents:

* ``menu.yaml`` — the org's priced work-item menu (required),
* ``rates.yaml`` — the rates contract (required),
* ``selections/*.yaml`` — one proposal per file; a single ``selection.yaml``
  beside ``menu.yaml`` is also accepted for one-proposal setups.

:func:`load_portfolio` reads the directory into a :class:`Portfolio`. Loading
is lenient by design: it fails (with :class:`PortfolioError`) only when a
required path is missing, a document cannot be read as an unambiguous YAML
mapping, or the reserved ``selections`` path is not a directory. Everything
else — schema violations, dangling references, over-allocation — is reported
by :func:`grantkit.menu.gates.run_gates`, so the CLI can print findings
instead of a stack trace.
"""

from __future__ import annotations

import math
from collections.abc import Hashable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from yaml.constructor import ConstructorError

from .schema import Menu, Rates, Selection


class PortfolioError(Exception):
    """A portfolio directory could not be read at all."""


_MERGE_KEY = object()
_NAN_KEY = object()


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys.

    Checking each mapping before SafeLoader expands YAML merge keys preserves
    the standard ``<<: *defaults`` override behavior while rejecting direct
    duplicate keys that PyYAML would otherwise resolve by keeping the last.
    """

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._duplicate_checked: set[int] = set()

    def flatten_mapping(self, node: Any) -> None:
        identity = id(node)
        if identity not in self._duplicate_checked:
            self._duplicate_checked.add(identity)
            seen: set[Any] = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    key: Any = _MERGE_KEY
                elif key_node.tag == "tag:yaml.org,2002:value":
                    key = key_node.value
                else:
                    key = self.construct_object(key_node, deep=True)
                if isinstance(key, float) and math.isnan(key):
                    key = _NAN_KEY
                if not isinstance(key, Hashable):
                    raise ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        "found unhashable key",
                        key_node.start_mark,
                    )
                if key in seen:
                    raise ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key ({key_node.value!r})",
                        key_node.start_mark,
                    )
                seen.add(key)
        super().flatten_mapping(node)


def _safe_load_unique(stream: Any) -> Any:
    """Load untrusted YAML with SafeLoader plus duplicate-key rejection."""
    loader = _UniqueKeySafeLoader(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _safe_load_unique(f)
    except yaml.YAMLError as exc:
        raise PortfolioError(f"Could not parse {path.name}: {exc}") from exc
    except RecursionError as exc:
        raise PortfolioError(
            f"Could not parse {path.name}: document nesting is too deep"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise PortfolioError(f"Could not read {path.name}: {exc}") from exc
    except MemoryError:
        raise
    except Exception as exc:
        # Some PyYAML scalar constructors leak ValueError/AttributeError for
        # hostile values instead of wrapping them in YAMLError. This is the
        # parser trust boundary, so normalize those failures for callers.
        raise PortfolioError(f"Could not parse {path.name}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PortfolioError(f"{path.name} must be a YAML mapping")
    return data


@dataclass
class Portfolio:
    """A loaded portfolio: menu + rates + selections.

    Raw dicts are kept for schema validation; the parsed objects are
    built leniently and are meaningful once the gates report no
    ``*_invalid`` errors.
    """

    root: Path
    menu_data: dict[str, Any]
    rates_data: dict[str, Any]
    selections_data: list[dict[str, Any]] = field(default_factory=list)
    menu: Menu = field(default_factory=Menu)
    rates: Rates = field(default_factory=Rates)
    selections: list[Selection] = field(default_factory=list)

    @property
    def selection_ids(self) -> list[str]:
        return [selection.id for selection in self.selections]

    def get_selection(self, selection_id: str) -> Optional[Selection]:
        for selection in self.selections:
            if selection.id == selection_id:
                return selection
        return None


def load_portfolio(path: str | Path) -> Portfolio:
    """Load a portfolio directory into a :class:`Portfolio`.

    Raises:
        PortfolioError: if a required path is missing, a document is not a
            readable, unambiguous YAML mapping, or ``selections`` exists but
            is not a directory.
    """
    root = Path(path)
    if not root.is_dir():
        raise PortfolioError(f"Portfolio directory not found: {root}")

    menu_path = root / "menu.yaml"
    rates_path = root / "rates.yaml"
    if not menu_path.exists():
        raise PortfolioError(f"No menu.yaml found in {root}")
    if not rates_path.exists():
        raise PortfolioError(f"No rates.yaml found in {root}")

    menu_data = _read_yaml_mapping(menu_path)
    rates_data = _read_yaml_mapping(rates_path)

    selection_paths: list[Path] = []
    single = root / "selection.yaml"
    if single.exists():
        selection_paths.append(single)
    selections_dir = root / "selections"
    if selections_dir.exists() and not selections_dir.is_dir():
        raise PortfolioError(
            f"Expected selections to be a directory: {selections_dir}"
        )
    if selections_dir.is_dir():
        selection_paths.extend(sorted(selections_dir.glob("*.yaml")))

    selections_data = [_read_yaml_mapping(p) for p in selection_paths]

    return Portfolio(
        root=root,
        menu_data=menu_data,
        rates_data=rates_data,
        selections_data=selections_data,
        menu=Menu.from_dict(menu_data),
        rates=Rates.from_dict(rates_data),
        selections=[Selection.from_dict(d) for d in selections_data],
    )
