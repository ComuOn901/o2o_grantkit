"""End-to-end tests for `grantkit budget` and the check wiring."""

import json
import os

import pytest
from click.testing import CliRunner

from grantkit.cli import main
from grantkit.core.checks import run_checks
from grantkit.core.project import GrantProject


def _invoke(*args):
    return CliRunner().invoke(main, ["budget", *map(str, args)])


def test_budget_help_uses_plain_terminal_markup():
    result = _invoke("--help")
    assert result.exit_code == 0
    assert "budget_model" in result.output
    assert "``budget_model:``" not in result.output


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


def test_budget_output_write_error_is_clean(make_portfolio, tmp_path):
    out = tmp_path / "missing" / "budget.md"
    result = _invoke(
        "--selection", "sel-live-a", "--output", out, make_portfolio()
    )
    assert result.exit_code == 2
    assert "Could not write budget document" in result.stderr
    assert "Traceback" not in result.output
    assert not out.exists()


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


def test_budget_json_with_output_writes_both(make_portfolio, tmp_path):
    out = tmp_path / "budget.md"
    result = _invoke(
        "--selection",
        "sel-live-a",
        "--json",
        "--output",
        out,
        make_portfolio(),
    )
    assert result.exit_code == 0
    assert "## Category summary" in out.read_text(encoding="utf-8")
    payload = json.loads(result.stdout)
    assert payload["total_usd"] == 245056.25
    assert "Wrote budget document" in result.stderr


def test_budget_json_rejects_narrative_without_output(make_portfolio):
    result = _invoke(
        "--selection", "sel-live-a", "--json", "--narrative", make_portfolio()
    )
    assert result.exit_code == 2
    assert "requires --output" in result.output


def test_budget_json_and_narrative_output_are_both_honored(
    make_portfolio, tmp_path
):
    out = tmp_path / "budget.md"
    result = _invoke(
        "--selection",
        "sel-live-a",
        "--json",
        "--narrative",
        "--output",
        out,
        make_portfolio(),
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["total_usd"] == 245056.25
    assert "## Narrative skeleton" in out.read_text(encoding="utf-8")


def test_budget_compile_surfaces_warnings_on_stderr(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["target_usd"] = 100000
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--selection", "sel-live-a", root)
    assert result.exit_code == 0  # warnings never block a compile
    assert "over_target" in result.stderr


def test_budget_json_stdout_pure_despite_warnings(
    make_portfolio, portfolio_selections
):
    # Warnings go to stderr so `budget --json | jq` keeps working.
    portfolio_selections[0]["target_usd"] = 100000
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--selection", "sel-live-a", "--json", root)
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total_usd"] == 245056.25
    assert "over_target" in result.stderr


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


def test_budget_malformed_menu_exit_2(make_portfolio):
    root = make_portfolio()
    (root / "menu.yaml").write_text("items: [unclosed\n", encoding="utf-8")
    result = _invoke("--check", root)
    assert result.exit_code == 2
    assert "Could not parse" in result.output


def test_budget_no_selections_exit_2(make_portfolio):
    result = _invoke(make_portfolio(selections=[]))
    assert result.exit_code == 2
    assert "has no selections" in result.output
    assert "selections/*.yaml" in result.output


def test_budget_compile_refuses_on_gate_errors(
    make_portfolio, portfolio_selections
):
    portfolio_selections[1]["selections"][0]["fraction"] = 0.6
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--selection", "sel-live-a", root)
    assert result.exit_code == 1
    assert "cofunding_over_allocated" in result.output


def test_budget_json_reports_gate_errors_as_json(
    make_portfolio, portfolio_selections
):
    portfolio_selections[0]["selections"].append(
        {"item": "zzz", "fraction": 0.1}
    )
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--selection", "sel-live-a", "--json", root)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert any(item["rule"] == "unknown_item" for item in payload["items"])
    assert "Cannot compile" in result.stderr


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


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_budget_check_json_rejects_non_finite_numbers(
    make_portfolio, portfolio_selections, value
):
    portfolio_selections[0]["selections"][0]["fraction"] = value
    root = make_portfolio(selections=portfolio_selections)
    result = _invoke("--check", "--json", root)
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["errors"] >= 1
    assert any(
        item["rule"] == "selection_invalid" for item in payload["items"]
    )
    assert "NaN" not in result.stdout
    assert "Infinity" not in result.stdout


def test_budget_check_warnings_exit_0(make_portfolio, portfolio_selections):
    portfolio_selections[0]["target_usd"] = 100000
    result = _invoke(
        "--check", make_portfolio(selections=portfolio_selections)
    )
    assert result.exit_code == 0
    assert "over_target" in result.output


def test_budget_check_empty_portfolio_passes(make_portfolio):
    result = _invoke("--check", make_portfolio(selections=[]))
    assert result.exit_code == 0


def test_budget_check_rejects_output_and_narrative_flags(
    make_portfolio, tmp_path
):
    root = make_portfolio()
    output_result = _invoke("--check", "--output", tmp_path / "x.md", root)
    narrative_result = _invoke("--check", "--narrative", root)
    assert output_result.exit_code == 2
    assert "--output cannot be used with --check" in output_result.output
    assert narrative_result.exit_code == 2
    assert "--narrative cannot be used with --check" in narrative_result.output


def test_budget_check_scopes_to_selection(
    make_portfolio, portfolio_selections
):
    # sel-draft references an unknown item; a check scoped to sel-live-a
    # skips that per-selection gate, while an unscoped check fails.
    portfolio_selections[2]["selections"].append(
        {"item": "zzz", "fraction": 0.1}
    )
    root = make_portfolio(selections=portfolio_selections)
    scoped = _invoke("--check", "--selection", "sel-live-a", root)
    assert scoped.exit_code == 0
    unscoped = _invoke("--check", root)
    assert unscoped.exit_code == 1


def test_budget_check_unknown_selection_id_fails(make_portfolio):
    result = _invoke("--check", "--selection", "ghost", make_portfolio())
    assert result.exit_code == 2
    assert "No selection 'ghost'" in result.output


# -- grant-project binding ----------------------------------------------


def _bound_grant(make_grant, portfolio_root, selection="sel-live-a", **extra):
    binding = {"portfolio": str(portfolio_root)}
    if selection is not None:
        binding["selection"] = selection
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
        "budget_model": binding,
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


def test_budget_binding_without_selection_single_proposal(
    make_grant, make_portfolio, portfolio_selections
):
    # A binding with no `selection:` key compiles a one-proposal
    # portfolio without needing --selection.
    portfolio_root = make_portfolio(
        selections=[], single_selection=portfolio_selections[0]
    )
    grant_root = _bound_grant(make_grant, portfolio_root, selection=None)
    result = _invoke(grant_root)
    assert result.exit_code == 0
    assert "sel-live-a" in result.output


def test_budget_binding_unknown_selection_exit_2(make_grant, make_portfolio):
    grant_root = _bound_grant(make_grant, make_portfolio(), selection="ghost")
    result = _invoke(grant_root)
    assert result.exit_code == 2
    assert "sel-live-a" in result.output  # lists what exists


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


def test_check_missing_selection_binding_has_clear_message(
    make_grant, make_portfolio
):
    grant_root = _bound_grant(make_grant, make_portfolio(), selection=None)
    result = run_checks(GrantProject(grant_root))
    hits = [item for item in result.items if item.rule == "unknown_selection"]
    assert len(hits) == 1
    assert "names no selection" in hits[0].message
    assert "'None'" not in hits[0].message
    assert "selection: <id>" in hits[0].message


def test_check_auto_binds_single_selection(
    make_grant, make_portfolio, portfolio_selections
):
    portfolio_root = make_portfolio(
        selections=[], single_selection=portfolio_selections[0]
    )
    grant_root = _bound_grant(make_grant, portfolio_root, selection=None)
    result = run_checks(GrantProject(grant_root))
    assert not [i for i in result.items if i.rule == "unknown_selection"]
    assert result.errors == 0


def test_check_binding_without_portfolio_key_is_an_error(make_grant):
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
        "budget_model": {"selection": "sel-live-a"},
    }
    grant_root = make_grant(
        config, {"responses/summary.md": "A tidy summary."}
    )
    result = run_checks(GrantProject(grant_root))
    hits = [i for i in result.items if i.rule == "budget_model_invalid"]
    assert len(hits) == 1
    assert hits[0].level == "error"


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
