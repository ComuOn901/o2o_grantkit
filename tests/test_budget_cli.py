"""End-to-end tests for `grantkit budget` and the check wiring."""

import json
import os

from click.testing import CliRunner

from grantkit.cli import main
from grantkit.core.checks import run_checks
from grantkit.core.project import GrantProject


def _invoke(*args):
    return CliRunner().invoke(main, ["budget", *map(str, args)])


# -- compile output modes -----------------------------------------------


def test_budget_prints_rich_tables(make_portfolio):
    result = _invoke("--selection", "sel-live-a", make_portfolio())
    assert result.exit_code == 0
    assert "sel-live-a" in result.output
    assert "Synthetic Fund A" in result.output
    assert "245,056" in result.output  # rounded total
    assert "Overhead" in result.output
    assert "49%" in result.output  # target fit


def test_budget_json_structure(make_portfolio):
    result = _invoke("--selection", "sel-live-a", "--json", make_portfolio())
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total_usd"] == 245056.25
    assert payload["generated_from"]["rates_provider"] == (
        "eggnest-employer 0.2.0"
    )
    assert payload["categories"]["org_base_usd"] == 120000.0
    assert payload["personnel"]["Encoding Lead"]["usd"] == 80000.0
    fractions = {
        item["item_id"]: item["fraction"] for item in payload["items"]
    }
    assert fractions == {"alpha": 0.5, "gamma-units": 0.5}


def test_budget_output_writes_markdown(make_portfolio, tmp_path):
    out = tmp_path / "budget.md"
    result = _invoke(
        "--selection", "sel-live-a", "--output", out, make_portfolio()
    )
    assert result.exit_code == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Budget — sel-live-a")
    assert "## Selected items" in text
    assert "## Personnel" in text
    assert "## Category summary" in text
    assert "eggnest-employer 0.2.0" in text
    assert "## Narrative skeleton" not in text  # only with --narrative


def test_budget_narrative_includes_evidence(make_portfolio):
    result = _invoke(
        "--selection", "sel-live-a", "--narrative", make_portfolio()
    )
    assert result.exit_code == 0
    assert "## Narrative skeleton" in result.output
    assert (
        "Completion evidence: Certified oracle suite green." in result.output
    )
    assert "## Budget justification" in result.output
    assert "BLS OEWS May 2024" in result.output


def test_budget_narrative_with_output_file(make_portfolio, tmp_path):
    out = tmp_path / "budget.md"
    result = _invoke(
        "--selection",
        "sel-live-a",
        "--narrative",
        "--output",
        out,
        make_portfolio(),
    )
    assert result.exit_code == 0
    assert "## Narrative skeleton" in out.read_text(encoding="utf-8")


def test_budget_markdown_deterministic(make_portfolio, tmp_path):
    root = make_portfolio()
    first, second = tmp_path / "a.md", tmp_path / "b.md"
    _invoke("--selection", "sel-live-a", "--output", first, root)
    _invoke("--selection", "sel-live-a", "--output", second, root)
    assert first.read_bytes() == second.read_bytes()


# -- selection resolution and exit codes --------------------------------


def test_budget_requires_selection_when_ambiguous(make_portfolio):
    result = _invoke(make_portfolio())
    assert result.exit_code == 2
    assert "--selection" in result.output
    assert "sel-live-a" in result.output


def test_budget_unknown_selection_exit_2(make_portfolio):
    result = _invoke("--selection", "nope", make_portfolio())
    assert result.exit_code == 2
    assert "sel-live-a" in result.output  # lists what exists


def test_budget_single_selection_needs_no_flag(
    make_portfolio, portfolio_selections
):
    root = make_portfolio(
        selections=[], single_selection=portfolio_selections[0]
    )
    result = _invoke(root)
    assert result.exit_code == 0
    assert "sel-live-a" in result.output


def test_budget_unreadable_portfolio_exit_2(tmp_path):
    result = _invoke(tmp_path)
    assert result.exit_code == 2


def test_budget_compile_refuses_on_gate_errors(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["selections"][0]["fraction"] = 0.6
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--selection", "sel-live-a", root)
    assert result.exit_code == 1
    assert "cofunding_over_allocated" in result.output


# -- budget --check -----------------------------------------------------


def test_budget_check_clean_exit_0(make_portfolio):
    result = _invoke("--check", make_portfolio())
    assert result.exit_code == 0
    assert "All checks passed" in result.output


def test_budget_check_errors_exit_1_with_json(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["selections"][0]["fraction"] = 0.6
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--check", "--json", root)
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["errors"] == 1
    rules = {item["rule"] for item in payload["items"]}
    assert "cofunding_over_allocated" in rules


def test_budget_check_warnings_exit_0(make_portfolio, portfolio_selections):
    portfolio_selections[0]["target_usd"] = 100000
    result = _invoke(
        "--check", make_portfolio(selections=portfolio_selections)
    )
    assert result.exit_code == 0
    assert "over_target" in result.output


# -- grant-project binding ----------------------------------------------


def _bound_grant(make_grant, portfolio_root, selection="sel-live-a", **extra):
    config = {
        "title": "Bound grant",
        "funder": "Test Foundation",
        "sections": [
            {
                "id": "summary",
                "title": "Summary",
                "required": True,
                "file": "responses/summary.md",
            }
        ],
        "budget_model": {
            "portfolio": str(portfolio_root),
            "selection": selection,
        },
        **extra,
    }
    return make_grant(
        config,
        {"responses/summary.md": "A tidy summary of the planned work."},
    )


def test_budget_uses_grant_project_binding(make_grant, make_portfolio):
    grant_root = _bound_grant(make_grant, make_portfolio())
    result = _invoke(grant_root)
    assert result.exit_code == 0
    assert "sel-live-a" in result.output


def test_budget_binding_relative_path(make_grant, make_portfolio):
    portfolio_root = make_portfolio()
    grant_root = _bound_grant(make_grant, portfolio_root)
    relative = os.path.relpath(portfolio_root, grant_root)
    config_path = grant_root / "grant.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            str(portfolio_root), relative
        ),
        encoding="utf-8",
    )
    result = _invoke(grant_root)
    assert result.exit_code == 0


def test_budget_selection_flag_overrides_binding(make_grant, make_portfolio):
    grant_root = _bound_grant(make_grant, make_portfolio())
    result = _invoke("--selection", "sel-live-b", grant_root)
    assert result.exit_code == 0
    assert "sel-live-b" in result.output


def test_budget_grant_without_binding_exit_2(make_grant, simple_config):
    grant_root = make_grant(
        simple_config,
        {
            "responses/summary.md": "Summary words.",
            "responses/narrative.md": "Narrative words.",
        },
    )
    result = _invoke(grant_root)
    assert result.exit_code == 2
    assert "budget_model" in result.output


# -- check wiring (_check_selection_model) ------------------------------


def test_check_runs_selection_gates(
    make_grant, make_portfolio, portfolio_selections
):
    portfolio_selections[1]["selections"][0]["fraction"] = 0.6
    portfolio_root = make_portfolio(selections=portfolio_selections)
    grant_root = _bound_grant(make_grant, portfolio_root)
    result = run_checks(GrantProject(grant_root))
    rules = {item.rule for item in result.items}
    assert "cofunding_over_allocated" in rules
    assert result.failed()

    runner_result = CliRunner().invoke(
        main, ["check", "--json", str(grant_root)]
    )
    assert runner_result.exit_code == 1
    payload = json.loads(runner_result.output)
    assert any(
        item["rule"] == "cofunding_over_allocated" for item in payload["items"]
    )


def test_check_clean_bound_project_passes(make_grant, make_portfolio):
    grant_root = _bound_grant(make_grant, make_portfolio())
    result = run_checks(GrantProject(grant_root))
    assert result.errors == 0


def test_check_unknown_selection_is_an_error(make_grant, make_portfolio):
    grant_root = _bound_grant(make_grant, make_portfolio(), selection="nope")
    result = run_checks(GrantProject(grant_root))
    hits = [i for i in result.items if i.rule == "unknown_selection"]
    assert len(hits) == 1
    assert "sel-live-a" in hits[0].message


def test_check_unreadable_portfolio_is_an_error(make_grant, tmp_path):
    grant_root = _bound_grant(make_grant, tmp_path / "nowhere")
    result = run_checks(GrantProject(grant_root))
    assert any(
        i.rule == "budget_model_unreadable" and i.level == "error"
        for i in result.items
    )


def test_check_pack_cap_fires_through_binding(
    make_grant, make_portfolio, portfolio_menu, portfolio_selections
):
    # A live selection that compiles past PBIF's published $2M cap.
    portfolio_menu["items"].append(
        {
            "id": "big-block",
            "type": "platform",
            "title": "Big block",
            "what": "A large costed block.",
            "evidence": "Delivered.",
            "status": "planned",
            "dependencies": [],
            "provenance": ["synthetic"],
            "resourcing": {"amount_usd": 3000000},
        }
    )
    portfolio_selections.append(
        {
            "schema": "grantkit-selection/v0",
            "id": "sel-big",
            "funder": "Synthetic Fund D",
            "status": "draft",
            "window_months": 12,
            "selections": [{"item": "big-block", "fraction": 1.0}],
        }
    )
    portfolio_root = make_portfolio(
        menu=portfolio_menu, selections=portfolio_selections
    )
    grant_root = _bound_grant(
        make_grant, portfolio_root, selection="sel-big", pack="pbif"
    )
    result = run_checks(GrantProject(grant_root))
    hits = [i for i in result.items if i.rule == "budget_over_total_cap"]
    assert len(hits) == 1
    assert hits[0].level == "error"
    assert "2,000,000" in hits[0].message
