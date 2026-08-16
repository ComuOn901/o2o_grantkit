"""Rendering for compiled budgets: rich tables, markdown, JSON, narrative.

Money is carried as floats through the engine; this module is where whole
dollars appear (round half up). The markdown budget document and the
narrative skeleton are rendered only from the compiled objects — connective
boilerplate aside, no prose is invented.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..core.checks import CheckResult
from .combine import CombinedCost
from .engine import SelectedItemCost, SelectionCost
from .loader import Portfolio
from .money import format_money, format_percent
from .money import round_half_up as round_half_up
from .schema import RoleRate, Selection

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_NARRATIVE_TEMPLATE = "budget_narrative.md.j2"


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
        + ". Compilation is deterministic for the same inputs."
    )


def _benchmark_text(role: Optional[RoleRate], currency: str) -> str:
    if role is None or role.benchmark is None:
        return ""
    benchmark = role.benchmark
    source = benchmark.source
    if not source:
        return ""
    text = str(source)
    if benchmark.percentile is not None:
        text += f", p{benchmark.percentile:g}"
    if benchmark.value_usd is not None:
        text += f" = {format_money(benchmark.value_usd, currency)}"
    return text


def _markdown_inline(value: str) -> str:
    """Keep a structural Markdown field on one line."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(normalized.split("\n"))


def _markdown_cell(value: str) -> str:
    """Escape table delimiters and preserve line breaks within one cell."""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("|", "&#124;").replace("\n", "<br>")


def _item_window_total(line: SelectedItemCost, cost: SelectionCost) -> Decimal:
    """Unweighted item total over the selection window, without overflow."""
    return Decimal(str(line.item.one_time_usd)) + (
        Decimal(str(line.item.recurring_usd_per_year))
        * Decimal(cost.window_months)
        / Decimal(12)
    )


# -- rich tables --------------------------------------------------------


def print_budget(
    console: Console,
    portfolio: Portfolio,
    selection: Selection,
    cost: SelectionCost,
    periods: bool = False,
) -> None:
    """Print the compiled budget as rich tables (the default output)."""
    currency = cost.currency
    console.print(
        Text.assemble((cost.selection_id, "bold"), " — ", cost.funder)
    )
    target = (
        f"target {format_money(cost.target_usd, currency)}"
        if cost.target_usd
        else "no target"
    )
    console.print(
        Text(
            f"{cost.status} · {cost.window_months}-month window · {target}",
            style="dim",
        )
    )
    console.print(Text(generated_from(portfolio) + "\n", style="dim"))

    items = Table(show_header=True, header_style="bold")
    items.add_column("Item")
    items.add_column("Type")
    items.add_column("Fraction", justify="right")
    items.add_column("Item cost", justify="right")
    items.add_column("Funded share", justify="right")
    for line in cost.items:
        item_total = _item_window_total(line, cost)
        items.add_row(
            Text(line.title),
            Text(line.type),
            Text(f"{line.fraction:g}"),
            Text(format_money(item_total, currency)),
            Text(format_money(line.funded_usd, currency)),
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
            personnel.add_row(*(Text(cell) for cell in cells))
        console.print(personnel)

    summary = Table(show_header=True, header_style="bold")
    summary.add_column("Category")
    summary.add_column("Amount", justify="right")
    for label, amount in _category_rows(cost):
        summary.add_row(Text(label), Text(format_money(amount, currency)))
    summary.add_row(
        Text("Total", style="bold"),
        Text(format_money(cost.total_usd, currency), style="bold"),
    )
    console.print(summary)

    if cost.fit is not None:
        console.print(
            Text.assemble(
                "\nTarget fit: ",
                (format_percent(cost.fit), "bold"),
                " of ",
                format_money(cost.target_usd or 0.0, currency),
                ".",
            )
        )
    if periods:
        _print_period_tables(console, portfolio, cost)
    if cost.revenue["by_stream"]:
        _print_revenue(console, cost)


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
        (
            f"Overhead ({format_percent(cost.overhead_rate)})",
            cost.overhead_usd,
        ),
    ]
    return [(label, amount) for label, amount in rows if amount]


def _print_period_tables(
    console: Console, portfolio: Portfolio, cost: SelectionCost
) -> None:
    currency = cost.currency
    phasing = Table(title="Phasing", show_header=True, header_style="bold")
    phasing.add_column("Period")
    phasing.add_column("Months", justify="right")
    for key, label in (
        ("labor", "Labor"),
        ("units", "Units"),
        ("contract", "Contract"),
        ("flat", "Flat"),
        ("recurring", "Recurring"),
        ("org_base", "Org base"),
        ("overhead", "Overhead"),
        ("total", "Total"),
    ):
        phasing.add_column(label, justify="right")
    for period in cost.periods:
        phasing.add_row(
            Text(str(period["label"])),
            Text(f"{period['months']:g}"),
            *(
                Text(format_money(period["cost"][key], currency))
                for key in (
                    "labor",
                    "units",
                    "contract",
                    "flat",
                    "recurring",
                    "org_base",
                    "overhead",
                    "total",
                )
            ),
        )
    console.print(phasing)

    rows = _staffing_rows(portfolio, cost)
    if not rows:
        return
    staffing = Table(title="Staffing", show_header=True, header_style="bold")
    staffing.add_column("Period")
    staffing.add_column("Role")
    staffing.add_column("Incremental FTE", justify="right")
    staffing.add_column("Base FTE", justify="right")
    staffing.add_column("Total FTE", justify="right")
    staffing.add_column("Capacity", justify="right")
    for row in rows:
        staffing.add_row(*(Text(cell) for cell in row))
    console.print(staffing)


def _staffing_rows(
    portfolio: Portfolio, cost: SelectionCost
) -> list[tuple[str, str, str, str, str, str]]:
    rates = portfolio.rates.roles_by_name
    rows: list[tuple[str, str, str, str, str, str]] = []
    for period in cost.periods:
        incremental = period["fte_by_role"]
        base = period["base_fte_by_role"]
        for role in sorted(set(incremental) | set(base)):
            incremental_fte = float(incremental.get(role, 0.0))
            base_fte = float(base.get(role, 0.0))
            rate = rates.get(role)
            capacity = rate.capacity_fte if rate is not None else None
            rows.append(
                (
                    str(period["label"]),
                    role,
                    f"{incremental_fte:g}",
                    f"{base_fte:g}",
                    f"{incremental_fte + base_fte:g}",
                    f"{capacity:g}" if capacity is not None else "—",
                )
            )
    return rows


def _print_revenue(console: Console, cost: SelectionCost) -> None:
    currency = cost.currency
    revenue = Table(title="Revenue", show_header=True, header_style="bold")
    revenue.add_column("Stream")
    revenue.add_column("Item")
    revenue.add_column("Enabled", justify="right")
    revenue.add_column("Attributed", justify="right")
    for stream in cost.revenue["by_stream"]:
        revenue.add_row(
            Text(str(stream["stream"])),
            Text(str(stream["item_id"])),
            Text(format_money(stream["enabled_usd"], currency)),
            Text(format_money(stream["attributed_usd"], currency)),
        )
    revenue.add_row(
        Text("Total", style="bold"),
        Text(""),
        Text(
            format_money(cost.revenue["enabled_total"], currency),
            style="bold",
        ),
        Text(
            format_money(cost.revenue["attributed_total"], currency),
            style="bold",
        ),
    )
    console.print(revenue)
    console.print(
        Text(
            "Net of attributed revenue — attribution is a convention; "
            "see docs: " + format_money(cost.net_of_attributed_usd, currency),
            style="dim",
        )
    )


def _period_markdown(portfolio: Portfolio, cost: SelectionCost) -> list[str]:
    currency = cost.currency
    lines = [
        "## Phasing",
        "",
        "| Period | Months | Labor | Units | Contract | Flat | Recurring "
        "| Org base | Overhead | Total |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for period in cost.periods:
        values = [
            str(period["label"]),
            f"{period['months']:g}",
            *(
                format_money(period["cost"][key], currency)
                for key in (
                    "labor",
                    "units",
                    "contract",
                    "flat",
                    "recurring",
                    "org_base",
                    "overhead",
                    "total",
                )
            ),
        ]
        lines.append(
            "| " + " | ".join(_markdown_cell(value) for value in values) + " |"
        )
    lines += ["", "## Staffing", ""]
    staffing = _staffing_rows(portfolio, cost)
    if not staffing:
        lines += ["No personnel are scheduled in these periods.", ""]
        return lines
    lines += [
        "| Period | Role | Incremental FTE | Base FTE | Total FTE | Capacity |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in staffing:
        lines.append(
            "| " + " | ".join(_markdown_cell(value) for value in row) + " |"
        )
    lines.append("")
    return lines


def _revenue_markdown(cost: SelectionCost) -> list[str]:
    currency = cost.currency
    lines = [
        "## Revenue",
        "",
        "Revenue streams are org-level projections, not a profit-and-loss "
        "statement. Attributed revenue scales enabled revenue by the "
        "selection fraction.",
        "",
        "| Stream | Item | Family | Enabled | Attributed |",
        "|---|---|---|---:|---:|",
    ]
    for stream in cost.revenue["by_stream"]:
        revenue_values = (
            str(stream["stream"]),
            str(stream["item_id"]),
            str(stream["family"] or "—"),
            format_money(stream["enabled_usd"], currency),
            format_money(stream["attributed_usd"], currency),
        )
        lines.append(
            "| "
            + " | ".join(_markdown_cell(value) for value in revenue_values)
            + " |"
        )
    lines += [
        "",
        "| Period | Enabled | Attributed |",
        "|---|---:|---:|",
    ]
    for period in cost.revenue["by_period"]:
        revenue_period_values = (
            str(period["label"]),
            format_money(period["enabled_usd"], currency),
            format_money(period["attributed_usd"], currency),
        )
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value) for value in revenue_period_values
            )
            + " |"
        )
    lines += [
        "",
        "Enabled revenue: "
        + _markdown_inline(
            format_money(cost.revenue["enabled_total"], currency)
        )
        + ".",
        "",
        "Attributed revenue: "
        + _markdown_inline(
            format_money(cost.revenue["attributed_total"], currency)
        )
        + ".",
        "",
        "Net of attributed revenue — attribution is a convention, see docs: "
        + _markdown_inline(format_money(cost.net_of_attributed_usd, currency))
        + ".",
        "",
    ]
    return lines


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


def combined_budget_json(
    portfolio: Portfolio,
    cost: CombinedCost,
    gates: CheckResult,
) -> dict[str, Any]:
    """The structured multi-selection rollup for ``budget --combine``."""
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
        "gates": gates.to_dict(),
    }


# -- markdown -----------------------------------------------------------


def budget_markdown(
    portfolio: Portfolio,
    selection: Selection,
    cost: SelectionCost,
    narrative: bool = False,
    periods: bool = False,
) -> str:
    """Render the markdown budget document (``budget --output``)."""
    currency = cost.currency
    lines = [
        f"# Budget — {_markdown_inline(cost.selection_id)}",
        "",
        f"- Funder: {_markdown_inline(cost.funder)}",
        f"- Status: {_markdown_inline(cost.status)}",
        f"- Window: {cost.window_months} months",
    ]
    if cost.target_usd:
        lines.append(
            "- Target: "
            + _markdown_inline(format_money(cost.target_usd, currency))
        )
    lines += ["", _markdown_inline(generated_from(portfolio)), ""]

    lines += [
        "## Selected items",
        "",
        "| Item | Type | Fraction | Item cost | Funded share |",
        "|---|---|---:|---:|---:|",
    ]
    for line in cost.items:
        item_total = _item_window_total(line, cost)
        item_cells = (
            line.title,
            line.type,
            f"{line.fraction:g}",
            format_money(item_total, currency),
            format_money(line.funded_usd, currency),
        )
        lines.append(
            "| "
            + " | ".join(_markdown_cell(cell) for cell in item_cells)
            + " |"
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
            personnel_cells = list(row[:4])
            if has_benchmarks:
                personnel_cells.append(row[4] or "—")
            lines.append(
                "| "
                + " | ".join(_markdown_cell(cell) for cell in personnel_cells)
                + " |"
            )
        lines.append("")

    lines += [
        "## Category summary",
        "",
        "| Category | Amount |",
        "|---|---:|",
    ]
    for label, amount in _category_rows(cost):
        category_cells = (label, format_money(amount, currency))
        lines.append(
            "| "
            + " | ".join(_markdown_cell(cell) for cell in category_cells)
            + " |"
        )
    lines.append(
        "| **Total** | **"
        + _markdown_cell(format_money(cost.total_usd, currency))
        + "** |"
    )
    lines.append("")
    if cost.fit is not None:
        lines += [
            f"Target fit: {format_percent(cost.fit)} of "
            f"{_markdown_inline(format_money(cost.target_usd or 0.0, currency))}.",
            "",
        ]

    if periods:
        lines += _period_markdown(portfolio, cost)
    if cost.revenue["by_stream"]:
        lines += _revenue_markdown(cost)

    if narrative:
        lines += [budget_narrative(portfolio, selection, cost), ""]
    return "\n".join(lines).rstrip() + "\n"


def combined_budget_markdown(
    portfolio: Portfolio,
    cost: CombinedCost,
    gates: CheckResult,
) -> str:
    """Render a deterministic Markdown funding rollup."""
    currency = cost.currency
    lines = [
        "# Combined budget",
        "",
        "- Packages: " + _markdown_inline(", ".join(cost.selection_ids)),
        "- Scenario: all selected packages are treated as live for gates",
        "",
        _markdown_inline(generated_from(portfolio)),
        "",
        "## Funding coverage",
        "",
    ]
    if not cost.org_bases:
        lines += ["No selected package claims an org base.", ""]
    for base in cost.org_bases:
        coverage = format_percent(float(base["coverage_fraction"]))
        lines += [
            f"### {_markdown_inline(str(base['title']))}",
            "",
            f"Core-ops coverage: **{coverage}**.",
            "",
            "| Source | Selection | Fraction | Pre-fee share |",
            "|---|---|---:|---:|",
        ]
        for share in base["shares"]:
            selection_id = share["selection_id"] or "—"
            coverage_cells = (
                str(share["funder"]),
                str(selection_id),
                format_percent(float(share["fraction"])),
                format_money(float(share["funded_usd"]), currency),
            )
            lines.append(
                "| "
                + " | ".join(_markdown_cell(cell) for cell in coverage_cells)
                + " |"
            )
        if base["over_allocated"]:
            lines += [
                "",
                "**OVER-ALLOCATED:** this org base exceeds 100% coverage; "
                "see the C2 gate below.",
            ]
        lines.append("")

    lines += [
        "## Item funding stacks",
        "",
        "| Item | Type | Funding stack | Σ fraction | Funded share | Gate |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in cost.items:
        stack = "; ".join(
            f"{share['funder']} ({share['selection_id']}): "
            f"{format_percent(float(share['fraction']))}"
            for share in item["shares"]
        )
        item_cells = (
            str(item["title"]),
            str(item["type"]),
            stack,
            format_percent(float(item["fraction"])),
            format_money(float(item["funded_usd"]), currency),
            "OVER-ALLOCATED" if item["over_allocated"] else "—",
        )
        lines.append(
            "| "
            + " | ".join(_markdown_cell(cell) for cell in item_cells)
            + " |"
        )
    lines.append("")

    if cost.personnel:
        lines += [
            "## Funded personnel",
            "",
            "| Role | Funded FTE-months | Loaded annual | Funded amount |",
            "|---|---:|---:|---:|",
        ]
        for role in sorted(cost.personnel):
            spend = cost.personnel[role]
            personnel_cells = (
                role,
                f"{spend['fte_months']:g}",
                format_money(spend["loaded_usd"], currency),
                format_money(spend["usd"], currency),
            )
            lines.append(
                "| "
                + " | ".join(_markdown_cell(cell) for cell in personnel_cells)
                + " |"
            )
        lines.append("")

    labels = {
        "labor_usd": "Labor",
        "units_usd": "Units",
        "contract_usd": "Contracts",
        "flat_usd": "Flat amounts",
        "recurring_usd": "Recurring (prorated)",
        "org_base_usd": "Org base",
        "overhead_usd": "Overhead",
    }
    lines += [
        "## Combined totals",
        "",
        "| Category | Amount |",
        "|---|---:|",
    ]
    for key, label in labels.items():
        amount = cost.categories[key]
        if amount:
            lines.append(
                f"| {_markdown_cell(label)} | "
                f"{_markdown_cell(format_money(amount, currency))} |"
            )
    lines += [
        "| **Total** | **"
        + _markdown_cell(format_money(cost.total_usd, currency))
        + "** |",
        "",
        "## Combined staffing",
        "",
        "Shared org-base rosters are counted once; incremental FTE is "
        "summed across packages.",
        "",
        "| Period | Role | Incremental FTE | Base FTE | Total FTE |",
        "|---|---|---:|---:|---:|",
    ]
    staffing_rows = 0
    for period in cost.periods:
        roles = sorted(period["total_fte_by_role"])
        for role in roles:
            staffing_rows += 1
            staffing_cells = (
                str(period["label"]),
                role,
                f"{period['fte_by_role'].get(role, 0.0):g}",
                f"{period['base_fte_by_role'].get(role, 0.0):g}",
                f"{period['total_fte_by_role'][role]:g}",
            )
            lines.append(
                "| "
                + " | ".join(_markdown_cell(cell) for cell in staffing_cells)
                + " |"
            )
    if not staffing_rows:
        lines.append("| — | No scheduled personnel | — | — | — |")
    lines.append("")

    if cost.revenue["by_stream"]:
        lines += [
            "## Combined revenue",
            "",
            "Enabled revenue for a shared stream is counted once; "
            "attributed revenue stacks with funded fractions.",
            "",
            "| Stream | Item | Enabled | Attributed |",
            "|---|---|---:|---:|",
        ]
        for stream in cost.revenue["by_stream"]:
            revenue_cells = (
                str(stream["stream"]),
                str(stream["item_id"]),
                format_money(stream["enabled_usd"], currency),
                format_money(stream["attributed_usd"], currency),
            )
            lines.append(
                "| "
                + " | ".join(_markdown_cell(cell) for cell in revenue_cells)
                + " |"
            )
        lines += [
            "| **Total** |  | **"
            + _markdown_cell(
                format_money(cost.revenue["enabled_total"], currency)
            )
            + "** | **"
            + _markdown_cell(
                format_money(cost.revenue["attributed_total"], currency)
            )
            + "** |",
            "",
        ]

    lines += [
        "## Gates",
        "",
        f"{gates.errors} error(s), {gates.warnings} warning(s).",
        "",
    ]
    if gates.items:
        lines += [
            "| Level | Rule | Selection | Finding |",
            "|---|---|---|---|",
        ]
        for finding in gates.items:
            gate_cells = (
                finding.level,
                finding.rule,
                finding.section or "—",
                finding.message,
            )
            lines.append(
                "| "
                + " | ".join(_markdown_cell(cell) for cell in gate_cells)
                + " |"
            )
        lines.append("")
    else:
        lines += ["No findings.", ""]
    return "\n".join(lines).rstrip() + "\n"


def budget_narrative(
    portfolio: Portfolio, selection: Selection, cost: SelectionCost
) -> str:
    """Render the narrative skeleton from the Jinja template."""
    currency = cost.currency
    roles = portfolio.rates.roles_by_name
    items = []
    for line in cost.items:
        if line.fraction <= 0:
            continue
        item = line.resolved
        if item is None or item.id != line.item_id:
            continue
        share = (
            f"{format_percent(line.fraction)} of "
            f"{format_money(_item_window_total(line, cost), currency)}"
            if line.fraction < 1
            else format_money(line.funded_usd, currency)
        )
        items.append(
            {
                "title": _markdown_inline(item.title),
                "what": item.what,
                "evidence": item.evidence,
                "cost_line": _markdown_inline(
                    (
                        f"{format_money(line.funded_usd, currency)} "
                        f"({share} at fraction {line.fraction:g})"
                        if line.fraction < 1
                        else format_money(line.funded_usd, currency)
                    )
                ),
                "revenue_enabled": (
                    _markdown_inline(
                        format_money(
                            sum(
                                stream["enabled_usd"]
                                for stream in cost.revenue["by_stream"]
                                if stream["item_id"] == line.item_id
                            ),
                            currency,
                        )
                    )
                    if item.revenue
                    else ""
                ),
            }
        )
    personnel = []
    for role, spend in cost.personnel.items():
        benchmark = _benchmark_text(roles.get(role), currency)
        personnel.append(
            {
                "role": _markdown_inline(role),
                "fte_months": f"{spend['fte_months']:g}",
                "loaded": _markdown_inline(
                    format_money(spend["loaded_usd"], currency)
                ),
                "usd": _markdown_inline(format_money(spend["usd"], currency)),
                "benchmark": (
                    _markdown_inline(f"Benchmark: {benchmark}.")
                    if benchmark
                    else ""
                ),
            }
        )
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.get_template(_NARRATIVE_TEMPLATE)
    return str(template.render(items=items, personnel=personnel))
