"""Backward-compatibility tests for compiled budget JSON."""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from grantkit.cli import main

FIXTURE_GOLDEN = (
    Path(__file__).parent / "golden" / "v03-fixture-sel-live-a.json"
)
REAL_PORTFOLIO = Path(
    "/Users/maxghenis/TheAxiomFoundation/" "axiom-roadmap-dashboard-yaml/menu"
)
REAL_GOLDEN = Path("/Users/maxghenis/GrantKit/v03-golden-oaif.json")
OAIF_TOTAL = 2578998.5666666664


def _invoke_json(portfolio: Path, selection_id: str) -> dict[str, Any]:
    result = CliRunner().invoke(
        main,
        [
            "budget",
            str(portfolio),
            "--selection",
            selection_id,
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _assert_golden_subset(actual: Any, expected: Any, path: str = "$") -> None:
    """Assert every legacy value while allowing new mapping keys."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a mapping"
        for key, expected_value in expected.items():
            assert key in actual, f"{path}: missing legacy key {key!r}"
            _assert_golden_subset(actual[key], expected_value, f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list"
        assert len(actual) == len(
            expected
        ), f"{path}: expected {len(expected)} entries, got {len(actual)}"
        for index, expected_value in enumerate(expected):
            _assert_golden_subset(
                actual[index], expected_value, f"{path}[{index}]"
            )
        return
    assert (
        actual == expected
    ), f"{path}: expected legacy value {expected!r}, got {actual!r}"


def test_v03_fixture_json_shared_keys_are_unchanged(make_portfolio):
    expected = json.loads(FIXTURE_GOLDEN.read_text(encoding="utf-8"))
    actual = _invoke_json(make_portfolio(), "sel-live-a")

    _assert_golden_subset(actual, expected)


@pytest.mark.skipif(
    not REAL_PORTFOLIO.is_dir() or not REAL_GOLDEN.is_file(),
    reason="local Axiom portfolio or v0.3 OAIF golden is unavailable",
)
def test_real_oaif_json_shared_keys_are_unchanged():
    expected = json.loads(REAL_GOLDEN.read_text(encoding="utf-8"))
    actual = _invoke_json(REAL_PORTFOLIO, "oaif-2026")

    _assert_golden_subset(actual, expected)
    assert actual["total_usd"] == OAIF_TOTAL
    print(f"oaif-2026 total_usd: {actual['total_usd']}")
