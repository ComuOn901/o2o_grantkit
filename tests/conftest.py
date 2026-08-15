"""Shared fixtures for the GrantKit engine tests."""

from pathlib import Path

import pytest
import yaml


def _write_grant(root: Path, config: dict, responses: dict) -> Path:
    """Write a grant.yaml plus response files under ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "grant.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    for rel, content in responses.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def make_grant(tmp_path):
    """Return a factory that writes a grant project and returns its root.

    Usage::

        root = make_grant(config={...}, responses={"responses/x.md": "..."})
    """
    counter = {"n": 0}

    def _factory(config: dict, responses: dict | None = None) -> Path:
        counter["n"] += 1
        root = tmp_path / f"grant{counter['n']}"
        return _write_grant(root, config, responses or {})

    return _factory


# -- budget-model portfolio fixtures ------------------------------------
#
# The synthetic portfolio mirrors the documented budget-model shapes:
# three roles (one with components + benchmark, one base-only, one
# loaded-only), six items (an org-base flat block with
# overhead_included, a units item, a recurring item, a dependency chain
# alpha -> beta, one shipped), and three selections (two live at
# 0.5 + 0.5 sharing an item — the co-funding boundary — plus a draft
# over-planner carrying an explicit-zero declaration). All values are
# synthetic; no org data.


def _portfolio_menu() -> dict:
    return {
        "schema": "grantkit-menu/v0",
        "currency": "USD",
        "overheads": {
            "fiscal_sponsorship_rate": 0.07,
            "provenance": "synthetic fiscal sponsorship for tests",
        },
        "unit_costs": {
            "module": {
                "usd_per_unit": 2.5,
                "derivation": "synthetic unit price",
                "provenance": ["synthetic"],
            }
        },
        "items": [
            {
                "id": "org-floor",
                "type": "org-base",
                "title": "Org floor",
                "what": "Keeps the org running.",
                "evidence": "Audited org budget published.",
                "status": "in-flight",
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "amount_usd": 1200000,
                    "overhead_included": True,
                },
            },
            {
                "id": "alpha",
                "type": "program-coverage",
                "title": "Alpha coverage",
                "what": "Full parity for program alpha.",
                "evidence": "Certified oracle suite green.",
                "status": "in-flight",
                "duration_months": 9,
                "dependencies": ["beta"],
                "provenance": ["synthetic"],
                "resourcing": {
                    "fte_months": {
                        "Encoding Lead": 6,
                        "Research Engineer": 3,
                    }
                },
            },
            {
                "id": "beta",
                "type": "platform",
                "title": "Beta platform",
                "what": "Platform base for alpha.",
                "evidence": "Release tagged and deployed.",
                "status": "in-flight",
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {
                    "fte_months": {"Program Lead": 4},
                    "contract_usd": 20000,
                },
            },
            {
                "id": "gamma-units",
                "type": "research-eval",
                "title": "Gamma evaluation",
                "what": "Module-priced evaluation run.",
                "evidence": "Evaluation report published.",
                "status": "planned",
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {"units": {"module": 10000}},
            },
            {
                "id": "delta-recurring",
                "type": "platform",
                "title": "Delta hosting",
                "what": "Recurring hosting and support.",
                "evidence": "Uptime dashboard live.",
                "status": "planned",
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {"recurring_usd_per_year": 60000},
            },
            {
                "id": "shipped-item",
                "type": "field",
                "title": "Shipped work",
                "what": "Already-delivered field work.",
                "evidence": "Deliverable archived.",
                "status": "shipped",
                "dependencies": [],
                "provenance": ["synthetic"],
                "resourcing": {"amount_usd": 50000},
            },
        ],
    }


def _portfolio_rates() -> dict:
    return {
        "schema": "grantkit-rates/v0",
        "provider": "eggnest-employer 0.2.0",
        "generated": "2026-08-15",
        "scenario": "synthetic-tests",
        "currency": "USD",
        "jurisdiction": "US-NY",
        "method": "Synthetic loaded-cost schedule for tests.",
        "roles": [
            {
                "role": "Encoding Lead",
                "loaded_usd": 320000,
                "base_usd": 240000,
                "soc": "15-1252",
                "components": [
                    {
                        "name": "employer_taxes",
                        "amount_usd": 18000,
                        "basis": "computed",
                        "source": "policyengine-us",
                    },
                    {
                        "name": "retirement",
                        "amount_usd": 47500,
                        "basis": "computed",
                        "source": "25% x base, IRC 415(c) cap",
                    },
                    {
                        "name": "benefits",
                        "amount_usd": 14500,
                        "basis": "configured",
                        "source": "scenario benefit schedule",
                    },
                ],
                "benchmark": {
                    "source": "BLS OEWS May 2024, SOC 15-1252, national",
                    "percentile": 75,
                    "value_usd": 130560,
                },
                "provenance": ["synthetic"],
            },
            {
                "role": "Research Engineer",
                "loaded_usd": 195000,
                "base_usd": 150000,
            },
            {"role": "Program Lead", "loaded_usd": 180000},
        ],
    }


def _portfolio_selections() -> list[dict]:
    return [
        {
            "schema": "grantkit-selection/v0",
            "id": "sel-live-a",
            "funder": "Synthetic Fund A",
            "status": "live",
            "target_usd": 500000,
            "window_months": 12,
            "org_base": {"item": "org-floor", "fraction": 0.1},
            "selections": [
                {"item": "alpha", "fraction": 0.5},
                {"item": "gamma-units", "fraction": 0.5},
            ],
        },
        {
            "schema": "grantkit-selection/v0",
            "id": "sel-live-b",
            "funder": "Synthetic Fund B",
            "status": "live",
            "window_months": 12,
            "selections": [
                {"item": "alpha", "fraction": 0.5},
                {"item": "delta-recurring", "fraction": 1.0},
            ],
        },
        {
            "schema": "grantkit-selection/v0",
            "id": "sel-draft",
            "funder": "Synthetic Fund C",
            "status": "draft",
            "window_months": 6,
            "selections": [
                {"item": "alpha", "fraction": 0.8},
                {
                    "item": "beta",
                    "fraction": 0.0,
                    "note": "declared, not billed here",
                },
            ],
        },
    ]


@pytest.fixture
def portfolio_menu():
    """A fresh copy of the synthetic menu.yaml dict."""
    return _portfolio_menu()


@pytest.fixture
def portfolio_rates():
    """A fresh copy of the synthetic rates.yaml dict."""
    return _portfolio_rates()


@pytest.fixture
def portfolio_selections():
    """Fresh copies of the three synthetic selection dicts."""
    return _portfolio_selections()


@pytest.fixture
def make_portfolio(tmp_path):
    """Return a factory that writes a portfolio dir and returns its root.

    Usage::

        root = make_portfolio()  # the synthetic default portfolio
        root = make_portfolio(menu={...}, selections=[{...}, ...])
        root = make_portfolio(single_selection={...})  # selection.yaml

    ``menu``/``rates``/``selections`` default to the synthetic
    portfolio; ``single_selection`` writes a lone ``selection.yaml``
    beside ``menu.yaml`` (pass ``selections=[]`` to make it the only
    proposal).
    """
    counter = {"n": 0}

    def _factory(
        menu: dict | None = None,
        rates: dict | None = None,
        selections: list[dict] | None = None,
        single_selection: dict | None = None,
    ) -> Path:
        counter["n"] += 1
        root = tmp_path / f"portfolio{counter['n']}"
        root.mkdir(parents=True, exist_ok=True)
        menu = _portfolio_menu() if menu is None else menu
        rates = _portfolio_rates() if rates is None else rates
        (root / "menu.yaml").write_text(
            yaml.safe_dump(menu, sort_keys=False), encoding="utf-8"
        )
        (root / "rates.yaml").write_text(
            yaml.safe_dump(rates, sort_keys=False), encoding="utf-8"
        )
        if single_selection is not None:
            (root / "selection.yaml").write_text(
                yaml.safe_dump(single_selection, sort_keys=False),
                encoding="utf-8",
            )
        if selections is None and single_selection is None:
            selections = _portfolio_selections()
        if selections:
            selections_dir = root / "selections"
            selections_dir.mkdir(exist_ok=True)
            for selection in selections:
                name = selection.get("id") or "selection"
                (selections_dir / f"{name}.yaml").write_text(
                    yaml.safe_dump(selection, sort_keys=False),
                    encoding="utf-8",
                )
        return root

    return _factory


@pytest.fixture
def simple_config():
    """A minimal, markdown-friendly grant config with two sections."""
    return {
        "title": "Test Grant",
        "funder": "Test Foundation",
        "program": "Test Program",
        "deadline": "2099-12-31",
        "accepts_markdown": True,
        "locale": "en-US",
        "sections": [
            {
                "id": "summary",
                "title": "Summary",
                "word_limit": 100,
                "required": True,
                "file": "responses/summary.md",
            },
            {
                "id": "narrative",
                "title": "Narrative",
                "word_limit": 50,
                "required": True,
                "file": "responses/narrative.md",
            },
        ],
    }
