"""Tests for portfolio discovery and loading error paths."""

import pytest

from grantkit.menu import PortfolioError, load_portfolio

# -- hard failures (PortfolioError) -------------------------------------


def test_missing_directory_raises(tmp_path):
    with pytest.raises(PortfolioError, match="not found"):
        load_portfolio(tmp_path / "nowhere")


def test_path_that_is_a_file_raises(tmp_path):
    file_path = tmp_path / "menu.yaml"
    file_path.write_text("schema: grantkit-menu/v0\n", encoding="utf-8")
    with pytest.raises(PortfolioError, match="not found"):
        load_portfolio(file_path)


def test_missing_menu_raises(make_portfolio):
    root = make_portfolio()
    (root / "menu.yaml").unlink()
    with pytest.raises(PortfolioError, match="No menu.yaml"):
        load_portfolio(root)


def test_missing_rates_raises(make_portfolio):
    root = make_portfolio()
    (root / "rates.yaml").unlink()
    with pytest.raises(PortfolioError, match="No rates.yaml"):
        load_portfolio(root)


def test_malformed_menu_yaml_raises(make_portfolio):
    root = make_portfolio()
    (root / "menu.yaml").write_text("items: [unclosed\n", encoding="utf-8")
    with pytest.raises(PortfolioError, match="Could not parse menu.yaml"):
        load_portfolio(root)


def test_malformed_selection_yaml_raises(make_portfolio):
    root = make_portfolio()
    bad = root / "selections" / "sel-live-a.yaml"
    bad.write_text("id: [oops\n", encoding="utf-8")
    with pytest.raises(PortfolioError, match="Could not parse"):
        load_portfolio(root)


def test_non_mapping_rates_yaml_raises(make_portfolio):
    root = make_portfolio()
    (root / "rates.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(PortfolioError, match="must be a YAML mapping"):
        load_portfolio(root)


# -- lenient loading ----------------------------------------------------


def test_empty_menu_yaml_loads_as_empty_mapping(make_portfolio):
    # An empty document is readable; the schema gates flag it, so the
    # CLI prints findings instead of a stack trace.
    root = make_portfolio()
    (root / "menu.yaml").write_text("", encoding="utf-8")
    portfolio = load_portfolio(root)
    assert portfolio.menu_data == {}
    assert portfolio.menu.items == []

    from grantkit.menu import run_gates

    items = run_gates(portfolio)
    assert items
    assert {item.rule for item in items} == {"menu_invalid"}


def test_single_selection_yaml_beside_menu(
    make_portfolio, portfolio_selections
):
    root = make_portfolio(
        selections=[], single_selection=portfolio_selections[0]
    )
    portfolio = load_portfolio(root)
    assert portfolio.selection_ids == ["sel-live-a"]
    selection = portfolio.get_selection("sel-live-a")
    assert selection is not None
    assert selection.funder == "Synthetic Fund A"


def test_selection_discovery_order(make_portfolio, portfolio_selections):
    # A lone selection.yaml loads first, then selections/*.yaml in
    # sorted filename order — deterministic discovery.
    single = dict(portfolio_selections[0])
    single["id"] = "zz-single"
    root = make_portfolio(
        selections=portfolio_selections, single_selection=single
    )
    portfolio = load_portfolio(root)
    assert portfolio.selection_ids == [
        "zz-single",
        "sel-draft",
        "sel-live-a",
        "sel-live-b",
    ]


def test_non_yaml_files_in_selections_ignored(make_portfolio):
    # Discovery is selections/*.yaml only: .yml and stray files are
    # not proposals.
    root = make_portfolio()
    (root / "selections" / "notes.txt").write_text(
        "not a selection", encoding="utf-8"
    )
    (root / "selections" / "sel-extra.yml").write_text(
        "id: sel-extra\n", encoding="utf-8"
    )
    portfolio = load_portfolio(root)
    assert "sel-extra" not in portfolio.selection_ids
    assert len(portfolio.selections) == 3


def test_portfolio_without_selections_loads(make_portfolio):
    root = make_portfolio(selections=[])
    portfolio = load_portfolio(root)
    assert portfolio.selections == []
    assert portfolio.selection_ids == []


def test_get_selection_missing_returns_none(make_portfolio):
    portfolio = load_portfolio(make_portfolio())
    assert portfolio.get_selection("ghost") is None
