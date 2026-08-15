# Budget model

`grantkit budget` compiles a proposal budget from three plain YAML
documents instead of a hand-maintained spreadsheet: your org's priced
**menu** of work items, a **rates** file from a rates provider, and one
**selection** per proposal. The compiled budget is a pure function of
those inputs — same files, same numbers, byte for byte — and the
integrity gates catch the failure mode spreadsheets invite: quietly
selling the same work twice.

GrantKit stays an engine here. It ships the schemas, the compiler, and
the gates; your menus, rates, and selections live in your own repos.
It validates structure and flags advisory heuristics, but it never
invents a funder limit and never recomputes your rates provider's
numbers (see [the rates contract](rates-contract.md)).

## The portfolio directory

A portfolio directory holds the three document kinds:

```
org-portfolio/
├── menu.yaml          # the priced work-item menu
├── rates.yaml         # loaded personnel rates (rates contract)
└── selections/
    ├── funder-a.yaml  # one proposal per file
    └── funder-b.yaml
```

For one-proposal setups a single `selection.yaml` beside `menu.yaml`
is also accepted.

```bash
grantkit budget org-portfolio --selection funder-a   # rich tables
grantkit budget org-portfolio --check                # gates only
```

## menu.yaml — the priced work-item menu

Schema marker: `schema: grantkit-menu/v0`.

```yaml
schema: grantkit-menu/v0
currency: USD
overheads:                      # org-level economics, applied at
  fiscal_sponsorship_rate: 0.07 # selection level (0..1)
  provenance: "PSL fiscal sponsorship, current agreement"
unit_costs:                     # named unit prices for resourcing.units
  module:
    usd_per_unit: 2.424
    derivation: "0.808 system $/accepted module x 3.0 uplift"
    provenance: ["planning doc 2026-07-11"]
items:
  - id: pe-parity-full          # required; unique; [a-z0-9-]+
    type: program-coverage      # required; free vocabulary
    title: "PE parity, full"    # required
    what: "One sentence on what this is."         # required
    evidence: "Machine-checkable done-evidence."  # required
    status: in-flight           # required: shipped|in-flight|planned
    duration_months: 9          # optional integer
    dependencies: []            # required list (may be empty);
                                # ids must resolve within the menu
    revenue_unlock: "..."       # optional free text
    provenance: ["..."]         # required non-empty list of sources
    resourcing:                 # required; at least one costed field
      fte_months:               # role -> months; roles must exist
        "Encoding Lead": 6      # in rates.yaml
      units:                    # unit name -> count; names must
        module: 16000           # exist in unit_costs
      contract_usd: 60000       # flat vendor/contract dollars
      recurring_usd_per_year: 40000   # accrues over the selection
                                      # window, prorated
      amount_usd: 14250000      # flat block (org-base shapes)
      overhead_included: true   # see below; default false
```

Recommended (not enforced) `type` vocabulary: `program-coverage`,
`platform`, `research-eval`, `field`, `org-base`. Only `org-base`
carries semantics: it is the one type a selection's `org_base` block
may point at.

### overhead_included

`overhead_included: true` is only meaningful with `amount_usd` /
`contract_usd`: it records that those dollars **already contain org
overheads**, so the selection-level overhead must not re-apply to
them. Upstream org models often emit fee-inclusive totals; re-applying
the fee on top produces a phantom overhead-on-overhead line (a real
$99,750 error on one live view motivated this flag). With the flag
set, the fee is applied exactly once, by construction. Labor and units
always remain overhead-bearing — they are raw costs.

## selection.yaml — a proposal as a selection over the menu

Schema marker: `schema: grantkit-selection/v0`. One file per proposal.

```yaml
schema: grantkit-selection/v0
id: oaif-2026                  # required; unique across the portfolio
funder: "Example Fund"         # required
status: live                   # required: draft|live|awarded|
                               #           withdrawn|declined
target_usd: 2000000            # optional advisory ask target
window_months: 16              # required integer > 0
org_base:                      # optional fractional org-base claim
  item: org-floor-std          # must resolve; item.type must be
  fraction: 0.10               # org-base; fraction in 0..1
selections:                    # ordered; explicit 0 fractions are
  - {item: pe-parity-full, fraction: 1.0}       # preserved
  - {item: abstention-evals, fraction: 0.0,
     note: "declared, not billed here"}         # note optional
notes: "..."                   # optional
```

An explicit `fraction: 0.0` line is a declaration — "this work exists
and this proposal knows about it" — that costs nothing and adds no
personnel rows, but stays visible in the compiled tables.

## The cost model

All money is carried as floats internally; rendering rounds to whole
dollars (half up) at output.

Per item:

```
labor    = sum over roles of fte_months/12 x loaded_usd
units    = sum over units of count x usd_per_unit
contract = contract_usd
flat     = amount_usd
one_time = labor + units + contract + flat   (recurring excluded)
```

Per selection:

```
work per line  = fraction x one_time
               + fraction x recurring_usd_per_year x window_months/12
org base       = fraction x one_time(org_base.item)
overhead       = rate x (everything except fee-inclusive amounts)
total          = work + org base + overhead
fit            = total / target_usd        (when a target is set)
```

Two deliberate choices, matching upstream practice:

- **The window does not prorate flat blocks.** An org-base claim is a
  fraction of a flat amount, not a run rate.
- **Recurring costs are prorated by the window** (`x window/12`) and
  are overhead-bearing.

## Integrity gates

`grantkit budget --check` (and `grantkit check` in a bound project)
runs the gates and reports findings in the standard check format.

Errors:

| Rule | Meaning |
|------|---------|
| `menu_invalid` / `rates_invalid` / `selection_invalid` | Schema violations, including a menu/rates currency mismatch and duplicate selection ids. These short-circuit the structural gates. |
| `unknown_item` | A selection line or `org_base` references a missing item id. |
| `unknown_role` | An item's `fte_months` role is missing from the rates. |
| `unknown_unit` | An item's unit name is missing from `unit_costs`. |
| `dependency_unresolved` | An item dependency id is missing from the menu. |
| `dependency_cycle` | The dependency graph has a cycle. |
| `fraction_out_of_range` | Any fraction below 0 or above 1. |
| `org_base_type` | `org_base.item` exists but its type is not `org-base`. |
| `selection_duplicate_item` | The same item appears twice in one selection. |
| `cofunding_over_allocated` | The co-funding gate — see below. |
| `budget_over_total_cap` | Bound rule pack only: the compiled total exceeds the funder's published total cap. |

Warnings (advisory heuristics, clearly labeled — not funder rules):

| Rule | Meaning |
|------|---------|
| `dependency_unfunded` | A funded item depends on `planned` work that no live/awarded selection (nor this one) funds. |
| `over_target` | The compiled total exceeds the advisory `target_usd` (a target is an ask, not a cap). |
| `load_factor_suspicious` / `components_mismatch` | Rates heuristics — see [the rates contract](rates-contract.md). |
| `budget_over_annual_cap` | Bound rule pack only: total x 12/window_months exceeds the funder's annual cap. A uniform-spread approximation, hence a warning — confirm against your actual phasing. |

### The co-funding gate

For each menu item, the fractions across all selections with status
`live` or `awarded` — including `org_base` fractions — must sum to at
most 1 (tolerance 1e-9, so two exact halves pass). The finding lists
every contributing selection and its fraction.

`draft`, `withdrawn`, and `declined` selections are excluded: drafts
are free to over-plan. The invariant binds simultaneous live
applications, and the gate fires the moment an over-planned draft goes
live.

## Binding a grant project

A grant project may bind itself to one selection in `grant.yaml`:

```yaml
budget_model:
  portfolio: ../org-portfolio   # relative to the grant directory
  selection: oaif-2026          # optional when the portfolio has
                                # exactly one selection
```

With a binding in place:

- `grantkit check` runs the portfolio gates alongside every other
  check, and applies the funder pack's `budget_rules` caps to the
  compiled selection total.
- `grantkit budget` in the grant directory compiles the bound
  selection with no flags.

## The budget verb

```
grantkit budget [PATH]
  --selection TEXT   selection id (required for multi-selection
                     portfolios unless PATH is a bound grant project)
  --check            run the gates only; exit 1 on errors, 2 on an
                     unreadable portfolio
  --json             emit the full structured compilation as JSON
  --output PATH      write the markdown budget document to a file
  --narrative        include the narrative skeleton in the markdown
                     (without --output, prints the markdown document)
```

The default output is rich tables: header with a generated-from
reproducibility line, selected items, personnel (with a benchmark
column when the rates carry benchmarks), and a category summary
(labor / units / contracts / flat / recurring / org base / overhead /
total, plus the target fit).

`--output` writes the same content as a markdown document. With
`--narrative` it appends a skeleton rendered from the compiled objects
only — per funded item, the title, `what`, the completion evidence,
and the cost; then a budget-justification line per role with the
benchmark provenance when present. No invented prose beyond
connective boilerplate.

## Scope

Out of scope in v0: multi-year phasing beyond window proration,
currency conversion (a menu/rates currency mismatch is a validation
error), emitting a legacy NSF-category `budget.yaml` from a selection
(a possible future bridge), and BLS validation of menu roles (the
existing salary validator remains `budget.yaml`-only).
