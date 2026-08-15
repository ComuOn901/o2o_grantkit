"""GrantKit command-line interface.

Six verbs, one engine:

* ``grantkit init``   — scaffold a grant project (optionally from a funder pack)
* ``grantkit check``  — lint the proposal (the linter)
* ``grantkit build``  — compile responses into one document (the compiler)
* ``grantkit review`` — emit a review packet for an AI agent
* ``grantkit status`` — completion, word counts, deadline countdown
* ``grantkit budget`` — compile a portfolio selection into a budget

The engine is stateless and local-first: it reads files, writes files, and
makes no network or AI calls (except opt-in link checking under
``check --urls`` and opt-in BLS/GSA lookups when those API keys are set).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .core.builder import BuildDependencyError, build_project
from .core.checks import CheckResult, run_checks
from .core.project import GrantProject
from .core.review import build_review
from .core.scaffold import ScaffoldError, init_project
from .core.status import build_status, days_until_deadline, write_status
from .menu import (
    Portfolio,
    PortfolioError,
    load_portfolio,
    run_gates,
    selection_cost,
)
from .menu.render import budget_json, budget_markdown, print_budget
from .menu.schema import Selection
from .packs import FunderPack

console = Console()
err_console = Console(stderr=True)

PATH_ARG = click.argument(
    "path",
    type=click.Path(file_okay=False, path_type=Path),
    default=".",
    required=False,
)


def _load_project(path: Path) -> GrantProject:
    grant_yaml = Path(path) / "grant.yaml"
    if not grant_yaml.exists():
        err_console.print(
            f"[red]No grant.yaml found in {Path(path).resolve()}[/red]\n"
            "Run [bold]grantkit init[/bold] to scaffold one."
        )
        raise SystemExit(2)
    return GrantProject(Path(path))


@click.group()
@click.version_option(__version__, prog_name="grantkit")
def main() -> None:
    """GrantKit — the linter and compiler for grant proposals."""


# -- init ---------------------------------------------------------------


@main.command()
@click.option(
    "--funder",
    "funder",
    default=None,
    help="Funder rule-pack id (e.g. nsf-pappg, nuffield-rda, pbif).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing grant.yaml / budget.yaml.",
)
@PATH_ARG
def init(funder: Optional[str], force: bool, path: Path) -> None:
    """Scaffold a new grant project."""
    try:
        created = init_project(Path(path), funder=funder, force=force)
    except ScaffoldError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    console.print(
        f"[green]Initialized grant project in {Path(path).resolve()}[/green]"
    )
    for file_path in created:
        try:
            rel = file_path.relative_to(Path(path).resolve())
        except ValueError:
            rel = file_path
        console.print(f"  [dim]created[/dim] {rel}")
    if funder:
        console.print(
            f"\nUsing funder pack [bold]{funder}[/bold]. "
            "Edit responses/, then run [bold]grantkit check[/bold]."
        )
    else:
        console.print(
            "\nEdit grant.yaml + responses/, then run "
            "[bold]grantkit check[/bold]."
        )


# -- check --------------------------------------------------------------


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@click.option("--strict", is_flag=True, help="Treat warnings as failures too.")
@click.option(
    "--urls",
    "check_urls",
    is_flag=True,
    help="Also check that URLs are reachable (makes network requests).",
)
@PATH_ARG
def check(as_json: bool, strict: bool, check_urls: bool, path: Path) -> None:
    """Lint the proposal; exit non-zero on errors (or warnings with --strict)."""
    project = _load_project(path)
    result = run_checks(project, strict=strict, check_urls=check_urls)

    if as_json:
        # Raw stdout so CI / agents capture clean JSON.
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
    else:
        _print_checks(result)

    raise SystemExit(1 if result.failed(strict=strict) else 0)


def _print_checks(result: CheckResult) -> None:
    if not result.items:
        console.print("[green]All checks passed.[/green]")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Level")
    table.add_column("Rule")
    table.add_column("Section")
    table.add_column("Message")
    for item in result.items:
        color = "red" if item.level == "error" else "yellow"
        table.add_row(
            f"[{color}]{item.level}[/{color}]",
            item.rule,
            item.section or "-",
            item.message,
        )
    console.print(table)
    console.print(
        f"\n[bold]{result.errors}[/bold] error(s), "
        f"[bold]{result.warnings}[/bold] warning(s)."
    )


# -- build --------------------------------------------------------------


@main.command()
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["md", "html", "pdf", "docx"]),
    default="md",
    help="Output format for the compiled document.",
)
@click.option(
    "--share",
    is_flag=True,
    help="Also write a self-contained assembled.html review page.",
)
@click.option(
    "--output",
    "output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path for the compiled document (default proposal.<format>).",
)
@PATH_ARG
def build(fmt: str, share: bool, output: Optional[Path], path: Path) -> None:
    """Assemble responses into one document (always writes status.json)."""
    project = _load_project(path)
    try:
        result = build_project(project, fmt=fmt, share=share, output=output)
    except BuildDependencyError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    console.print("[green]Build complete.[/green]")
    for out in result.outputs():
        try:
            rel = out.relative_to(Path(path).resolve())
        except ValueError:
            rel = out
        console.print(f"  [dim]wrote[/dim] {rel}")


# -- review -------------------------------------------------------------


@main.command()
@click.option(
    "--pack",
    "include_pack",
    is_flag=True,
    help="Embed the full funder rule pack, not just the rubric.",
)
@click.option(
    "--output",
    "output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the packet to a file instead of stdout.",
)
@PATH_ARG
def review(include_pack: bool, output: Optional[Path], path: Path) -> None:
    """Emit a structured review packet for an AI agent (no AI calls)."""
    project = _load_project(path)
    packet = build_review(project, include_pack=include_pack)
    payload = json.dumps(packet, indent=2) + "\n"
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        console.print(f"[green]Wrote review packet to {output}[/green]")
    else:
        # Raw stdout so the packet pipes cleanly into an agent.
        sys.stdout.write(payload)


# -- status -------------------------------------------------------------


@main.command()
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Write status.json (and print it).",
)
@PATH_ARG
def status(as_json: bool, path: Path) -> None:
    """Show completion %, per-section word counts, and deadline countdown."""
    project = _load_project(path)

    if as_json:
        write_status(project)
        payload = build_status(project)
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return

    _print_status(project)


def _print_status(project: GrantProject) -> None:
    console.print(f"[bold]{project.title or project.funder or 'Grant'}[/bold]")
    if project.program:
        console.print(f"[dim]{project.program}[/dim]")

    countdown = days_until_deadline(project.deadline)
    if project.deadline:
        if countdown is None:
            when = project.deadline
        elif countdown < 0:
            when = f"{project.deadline} ({abs(countdown)} days ago)"
        else:
            when = f"{project.deadline} (in {countdown} days)"
        console.print(f"Deadline: {when}")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Section")
    table.add_column("Words", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Status")
    for section in project.sections:
        badge = {
            "complete": "[green]complete[/green]",
            "partial": "[yellow]partial[/yellow]",
            "empty": "[dim]empty[/dim]",
            "over_limit": "[red]over limit[/red]",
        }.get(section.status, section.status)
        table.add_row(
            section.title,
            str(section.words),
            str(section.word_limit or "-"),
            badge,
        )
    console.print(table)
    console.print(
        f"\n[bold]{project.completion_percent:.0f}%[/bold] complete — "
        f"{project.sections_complete}/{project.sections_total} sections, "
        f"{project.total_words:,} words."
    )


# -- budget -------------------------------------------------------------


@main.command()
@click.option(
    "--selection",
    "selection_id",
    default=None,
    help=(
        "Selection id to compile (required for multi-selection "
        "portfolios unless the path is a grant project bound to one)."
    ),
)
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    help=(
        "Run the integrity gates only; exit 1 on errors (2 on an "
        "unreadable portfolio)."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the full structured compilation (or gate findings) as JSON.",
)
@click.option(
    "--output",
    "output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the markdown budget document to a file.",
)
@click.option(
    "--narrative",
    is_flag=True,
    help=(
        "Include the narrative skeleton in the markdown output (without "
        "--output, prints the markdown document to stdout)."
    ),
)
@PATH_ARG
def budget(
    selection_id: Optional[str],
    check_only: bool,
    as_json: bool,
    output: Optional[Path],
    narrative: bool,
    path: Path,
) -> None:
    """Compile a portfolio selection into a budget (menu x rates).

    PATH is a portfolio directory (menu.yaml + rates.yaml + selections/)
    or a grant project whose grant.yaml binds one via ``budget_model:``.
    """
    portfolio, selection_id, pack = _load_portfolio_target(path, selection_id)

    if check_only:
        if selection_id is not None:
            _resolve_selection(portfolio, selection_id)
        result = CheckResult(items=run_gates(portfolio, selection_id, pack))
        if as_json:
            sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
        else:
            _print_checks(result)
        raise SystemExit(1 if result.failed() else 0)

    selection = _resolve_selection(portfolio, selection_id)
    result = CheckResult(items=run_gates(portfolio, selection.id, pack))
    if result.errors:
        _print_checks(result)
        err_console.print(
            "[red]Cannot compile: fix the errors above (or run "
            "budget --check).[/red]"
        )
        raise SystemExit(1)
    for item in result.items:
        err_console.print(
            f"[yellow]warning[/yellow] {item.rule}: {item.message}"
        )

    cost = selection_cost(selection, portfolio)
    if output:
        payload = budget_markdown(
            portfolio, selection, cost, narrative=narrative
        )
        Path(output).write_text(payload, encoding="utf-8")
        console.print(f"[green]Wrote budget document to {output}[/green]")
    if as_json:
        payload_json = budget_json(portfolio, selection, cost)
        sys.stdout.write(json.dumps(payload_json, indent=2) + "\n")
    elif narrative and not output:
        sys.stdout.write(
            budget_markdown(portfolio, selection, cost, narrative=True)
        )
    elif not output:
        print_budget(console, portfolio, selection, cost)


def _load_portfolio_target(
    path: Path, selection_id: Optional[str]
) -> tuple[Portfolio, Optional[str], Optional[FunderPack]]:
    """Resolve PATH to (portfolio, selection id, pack).

    PATH may be a portfolio directory or a grant project bound to one
    via ``budget_model:``. Exits 2 when neither is readable.
    """
    pack = None
    portfolio_dir = Path(path)
    if (Path(path) / "grant.yaml").exists():
        project = GrantProject(Path(path))
        binding = project.budget_model
        if not binding or not binding.get("portfolio"):
            err_console.print(
                f"[red]{project.grant_yaml_path} has no budget_model "
                "binding.[/red]\nAdd one:\n\n"
                "  budget_model:\n"
                "    portfolio: ../org-portfolio\n"
                "    selection: my-proposal\n\n"
                "or point grantkit budget at a portfolio directory."
            )
            raise SystemExit(2)
        portfolio_dir = (project.root / str(binding["portfolio"])).resolve()
        if selection_id is None:
            bound = binding.get("selection")
            selection_id = str(bound) if bound is not None else None
        pack = project.pack
    try:
        portfolio = load_portfolio(portfolio_dir)
    except PortfolioError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)
    return portfolio, selection_id, pack


def _resolve_selection(
    portfolio: Portfolio, selection_id: Optional[str]
) -> Selection:
    """Pick the selection to compile; exits 2 when ambiguous/unknown."""
    if selection_id is None:
        if len(portfolio.selections) == 1:
            return portfolio.selections[0]
        available = ", ".join(portfolio.selection_ids) or "(none)"
        err_console.print(
            "[red]This portfolio has "
            f"{len(portfolio.selections)} selections; pass "
            f"--selection ID.[/red]\nAvailable: {available}"
        )
        raise SystemExit(2)
    selection = portfolio.get_selection(selection_id)
    if selection is None:
        available = ", ".join(portfolio.selection_ids) or "(none)"
        err_console.print(
            f"[red]No selection '{selection_id}' in this portfolio."
            f"[/red]\nAvailable: {available}"
        )
        raise SystemExit(2)
    return selection


if __name__ == "__main__":  # pragma: no cover
    main()
