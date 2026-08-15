"""Rendering for compiled budgets: rich tables, markdown, JSON, narrative.

Money is carried as floats through the engine; this module is where whole
dollars appear (round half up). The markdown budget document and the
narrative skeleton are rendered only from the compiled objects — connective
boilerplate aside, no prose is invented.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.table import Table

from .engine import SelectionCost
from .loader import Portfolio
from .schema import RoleRate, Selection

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_NARRATIVE_TEMPLATE = "budget_narrative.md.j2"


def round_half_up(value: float) -> int:
    """Round to a whole dollar, half up (not banker's rounding)."""
    return int(
        Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def format_money(value: float, currency: str) -> str:
    """Format a float as whole currency units, e.g. ``USD 245,056``."""
    return f"{currency} {round_half_up(value):,}"


def generated_from(portfolio: Portfolio) -> str:
    """One reproducibility line naming the inputs the budget came from."""
    rates = portfolio.rates
    menu = portfolio.menu
    parts = [
        f"menu ({menu.schema}, {menu.currency})",
        f"rates by {rates.provider or 'unknown provider'}"
        + (f", {rates.generated}" if rates.generated else ""),
    ]
    if rates.scenario:
        parts.append(f"scenario {rates.scenario}")
    return (
        "Generated from "
        + "; ".join(parts)
        + ". Same inputs produce the same document."
    )


def _benchmark_text(role: Optional[RoleRate], currency: str) -> str:
    if role is None or role.benchmark is None:
        return ""
    benchmark = role.benchmark
    source = benchmark.source
    if not source:
        return ""
    text = source
    if benchmark.percentile is not None:
        text += f", p{benchmark.percentile:g}"
    if benchmark.value_usd is not None:
        text += f" = {format_money(benchmark.value_usd, currency)}"
    return text


# -- rich tables --------------------------------------------------------


def print_budget(
    console: Console,
    portfolio: Portfolio,
    selection: Selection,
    cost: SelectionCost,
) -> None:
    """Print the compiled budget as rich tables (the default output)."""
    currency = cost.currency
    console.print(f"[bold]{cost.selection_id}[/bold] — {cost.funder}")
    console.print(
        f"[dim]{cost.status} · {cost.window_months}-month window · "
        + (
            f"target {format_money(cost.target_usd, currency)}"
            if cost.target_usd
            else "no target"
        )
        + "[/dim]"
    )
    console.print(f"[dim]{generated_from(portfolio)}[/dim]\n")

    items = Table(show_header=True, header_style="bold")
    items.add_column("Item")
    items.add_column("Type")
    items.add_column("Fraction", justify="right")
    items.add_column("Item cost", justify="right")
    items.add_column("Funded share", justify="right")
    for line in cost.items:
        item_total = (
            line.item.one_time_usd
            + line.item.recurring_usd_per_year * cost.window_months / 12.0
        )
        items.add_row(
            line.title,
            line.type,
            f"{line.fraction:g}",
            format_money(item_total, currency),
            format_money(line.funded_usd, currency),
        )
    console.print(items)

    if cost.personnel:
        with_benchmarks = _personnel_rows(portfolio, cost)
        personnel = Table(show_header=True, header_style="bold")
        personnel.add_column("Role")
        personnel.add_column("FTE-months", justify="right")
        personnel.add_column("Loaded annual", justify="right")
        personnel.add_column("Amount", justify="right")
        has_benchmarks = any(row[4] for row in with_benchmarks)
        if has_benchmarks:
            personnel.add_column("Benchmark")
        for row in with_benchmarks:
            cells = list(row[:4])
            if has_benchmarks:
                cells.append(row[4])
            personnel.add_row(*cells)
        console.print(personnel)

    summary = Table(show_header=True, header_style="bold")
    summary.add_column("Category")
    summary.add_column("Amount", justify="right")
    for label, amount in _category_rows(cost):
        summary.add_row(label, format_money(amount, currency))
    summary.add_row(
        "[bold]Total[/bold]",
        f"[bold]{format_money(cost.total_usd, currency)}[/bold]",
    )
    console.print(summary)

    if cost.fit is not None:
        console.print(
            f"\nTarget fit: [bold]{cost.fit:.0%}[/bold] of "
            f"{format_money(cost.target_usd or 0.0, currency)}."
        )


def _personnel_rows(
    portfolio: Portfolio, cost: SelectionCost
) -> list[tuple[str, str, str, str, str]]:
    currency = cost.currency
    roles = portfolio.rates.roles_by_name
    rows: list[tuple[str, str, str, str, str]] = []
    for role, spend in cost.personnel.items():
        rows.append(
            (
                role,
                f"{spend['fte_months']:g}",
                format_money(spend["loaded_usd"], currency),
                format_money(spend["usd"], currency),
                _benchmark_text(roles.get(role), currency),
            )
        )
    return rows


def _category_rows(cost: SelectionCost) -> list[tuple[str, float]]:
    rows = [
        ("Labor", cost.labor_usd),
        ("Units", cost.units_usd),
        ("Contracts", cost.contract_usd),
        ("Flat amounts", cost.flat_usd),
        ("Recurring (prorated)", cost.recurring_usd),
        ("Org base", cost.org_base_usd),
        (f"Overhead ({cost.overhead_rate:.0%})", cost.overhead_usd),
    ]
    return [(label, amount) for label, amount in rows if amount]


# -- JSON ---------------------------------------------------------------


def budget_json(
    portfolio: Portfolio, selection: Selection, cost: SelectionCost
) -> dict[str, Any]:
    """The full structured compilation, for ``budget --json``."""
    rates = portfolio.rates
    menu = portfolio.menu
    return {
        "generated_from": {
            "menu_schema": menu.schema,
            "currency": menu.currency,
            "rates_provider": rates.provider,
            "rates_generated": rates.generated,
            "rates_scenario": rates.scenario,
        },
        **cost.to_dict(),
    }


# -- markdown -----------------------------------------------------------


def budget_markdown(
    portfolio: Portfolio,
    selection: Selection,
    cost: SelectionCost,
    narrative: bool = False,
) -> str:
    """Render the markdown budget document (``budget --output``)."""
    currency = cost.currency
    lines = [
        f"# Budget — {cost.selection_id}",
        "",
        f"- Funder: {cost.funder}",
        f"- Status: {cost.status}",
        f"- Window: {cost.window_months} months",
    ]
    if cost.target_usd:
        lines.append(f"- Target: {format_money(cost.target_usd, currency)}")
    lines += ["", generated_from(portfolio), ""]

    lines += [
        "## Selected items",
        "",
        "| Item | Type | Fraction | Item cost | Funded share |",
        "|---|---|---:|---:|---:|",
    ]
    for line in cost.items:
        item_total = (
            line.item.one_time_usd
            + line.item.recurring_usd_per_year * cost.window_months / 12.0
        )
        lines.append(
            f"| {line.title} | {line.type} | {line.fraction:g} | "
            f"{format_money(item_total, currency)} | "
            f"{format_money(line.funded_usd, currency)} |"
        )
    lines.append("")

    if cost.personnel:
        rows = _personnel_rows(portfolio, cost)
        has_benchmarks = any(row[4] for row in rows)
        header = "| Role | FTE-months | Loaded annual | Amount |"
        rule = "|---|---:|---:|---:|"
        if has_benchmarks:
            header += " Benchmark |"
            rule += "---|"
        lines += ["## Personnel", "", header, rule]
        for row in rows:
            cells = list(row[:4])
            if has_benchmarks:
                cells.append(row[4] or "—")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    lines += [
        "## Category summary",
        "",
        "| Category | Amount |",
        "|---|---:|",
    ]
    for label, amount in _category_rows(cost):
        lines.append(f"| {label} | {format_money(amount, currency)} |")
    lines.append(
        f"| **Total** | **{format_money(cost.total_usd, currency)}** |"
    )
    lines.append("")
    if cost.fit is not None:
        lines += [
            f"Target fit: {cost.fit:.0%} of "
            f"{format_money(cost.target_usd or 0.0, currency)}.",
            "",
        ]

    if narrative:
        lines += [budget_narrative(portfolio, selection, cost), ""]
    return "\n".join(lines).rstrip() + "\n"


def budget_narrative(
    portfolio: Portfolio, selection: Selection, cost: SelectionCost
) -> str:
    """Render the narrative skeleton from the Jinja template."""
    currency = cost.currency
    menu_items = portfolio.menu.items_by_id
    roles = portfolio.rates.roles_by_name
    items = []
    for line in cost.items:
        if line.fraction <= 0:
            continue
        item = menu_items.get(line.item_id)
        if item is None:
            continue
        share = (
            f"{line.fraction:.0%} of "
            f"{format_money(line.funded_usd / line.fraction, currency)}"
            if line.fraction < 1
            else format_money(line.funded_usd, currency)
        )
        items.append(
            {
                "title": item.title,
                "what": item.what,
                "evidence": item.evidence,
                "cost_line": (
                    f"{format_money(line.funded_usd, currency)} "
                    f"({share} at fraction {line.fraction:g})"
                    if line.fraction < 1
                    else format_money(line.funded_usd, currency)
                ),
            }
        )
    personnel = []
    for role, spend in cost.personnel.items():
        benchmark = _benchmark_text(roles.get(role), currency)
        personnel.append(
            {
                "role": role,
                "fte_months": f"{spend['fte_months']:g}",
                "loaded": format_money(spend["loaded_usd"], currency),
                "usd": format_money(spend["usd"], currency),
                "benchmark": (f"Benchmark: {benchmark}." if benchmark else ""),
            }
        )
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.get_template(_NARRATIVE_TEMPLATE)
    return template.render(items=items, personnel=personnel)
