# Budget model

`grantkit budget` compiles a proposal budget from three plain YAML
documents instead of a hand-maintained spreadsheet: your org's priced
**menu** of work items, a **rates** file from a rates provider, and one
**selection** per proposal. The compiled budget is a pure function of
those inputs: structured JSON and saved Markdown are deterministic; the
interactive Rich table adapts to terminal width. The
integrity gates catch the failure mode spreadsheets invite: quietly
selling the same work twice.

GrantKit stays an engine here. It ships the schemas, the compiler, and
the gates; your menus, rates, and selections live in your own repos.
It validates structure and flags advisory heuristics, but it never
invents a funder limit and never recomputes your rates provider's
numbers (see [the rates contract](rates-contract.md)).

The current schema markers are `grantkit-menu/v1`, `grantkit-rates/v1`,
and `grantkit-selection/v1`. GrantKit still accepts every v0 document, and a
v0 portfolio follows the v0.3 arithmetic exactly. A document that uses a
v1-only construct must declare the matching v1 marker; validation names both
the construct and required marker.
The schemas tolerate unknown keys so producers can carry extensions. Unknown
keys are not guessed: use the documented spellings exactly, especially
`overhead_included`, because a misspelling leaves its default (`false`) in
effect and can reapply overhead.

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

Portfolio files must be UTF-8 YAML mappings. Duplicate mapping keys are
rejected instead of silently taking the last value; YAML aliases and standard
merge-key overrides remain supported. A path named `selections`, when present,
must be a directory.

```bash
grantkit budget org-portfolio --selection funder-a   # rich tables
grantkit budget org-portfolio --check                # gates only
```

## menu.yaml — the priced work-item menu

Schema marker: `schema: grantkit-menu/v1` (`grantkit-menu/v0` is accepted).

```yaml
schema: grantkit-menu/v1
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
    duration_months: 9          # optional non-negative integer; 0 is instant
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

For ordinary items, `overhead_included: true` is meaningful with
`amount_usd` / `contract_usd`: it records that those dollars **already
contain org overheads**, so the selection-level overhead must not re-apply
to them. Upstream org models often emit fee-inclusive totals; re-applying
the fee on top produces a phantom overhead-on-overhead line (a real $99,750
error on one live view motivated this flag). Ordinary labor and units remain
overhead-bearing because they are raw costs. Roster labor and non-personnel
lines in a new bottoms-up org base are also raw costs. Such a base omits
`overhead_included`, so the selection-level fee applies once to its pre-fee
inputs. Existing fee-inclusive blocks retain the legacy flag contract.

## Estimate objects

V1 accepts an estimate object anywhere the budget model accepts an
uncertain, non-negative cost parameter. This includes `usd_per_unit`,
`fte_months`, contract, recurring and flat dollar leaves, kind FORM
coefficients, and revenue price and volume:

```yaml
usd_per_unit:
  central: 2.424
  low: 0.808
  high: 6.008
  basis: assumed
  source: "planning review, 2026-07-11"
```

`central` is required, finite, and non-negative. When supplied, the bounds
must satisfy `low <= central <= high`. `basis` is one of `computed`,
`configured`, or `assumed`; `source` is free text. GrantKit v0.4 always
uses `central` in arithmetic and does not sample a distribution. It carries
the complete metadata (`central`, bounds, basis, and source) into the
compiled JSON's flat `estimates` mapping. The model export likewise retains
the estimate beside its central value.

This metadata is the designated extension point for a future seeded
PERT/Monte Carlo sampler. It does not change today's total. Fractions,
selection and schedule months, and count parameters remain plain numbers:
they are package decisions, not uncertainty estimates.

## Parametric kinds

`kinds` turn a named parameter bundle into a concrete item. The compiler
resolves the kind before costing it, so the rest of the engine consumes the
same concrete shape as a traditional menu item.

```yaml
kinds:
  program-coverage:
    title: "Program coverage"
    params:
      program: {type: string, default: SNAP}
      jurisdictions:
        {type: integer, min: 1, max: 56, default: 1}
      tier:
        {type: enum, values: [encoded, certified], default: encoded}
      qc_data_available: {type: boolean, default: true}
      modules_per_jurisdiction:
        {type: number, min: 0, default: 300}
    derived:
      modules:
        {product: [modules_per_jurisdiction, jurisdictions]}
    resourcing:
      units:
        module: {per: {modules: 1}}
      fte_months:
        "Encoding Lead":
          {per: {modules: 0.000375, jurisdictions: 0.2}}
        "Research Scientist":
          - {per: {jurisdictions: 0.4},
             when: {qc_data_available: [true]}}
          - {per: {jurisdictions: 0.8},
             when: {qc_data_available: [false]}}
    duration_months: {const: 3, per: {jurisdictions: 0.5}}
    dependencies:
      by:
        tier: {certified: [cert-ladder]}
    title_template: "{program} {tier}, {jurisdictions} jurisdictions"
```

Every parameter declares a `type` and a required `default`. Supported types
are `number`, `integer`, `enum`, `boolean`, and `string`. Numeric definitions
may set inclusive `min` and `max` bounds. An omitted or null numeric `min`
defaults to `0`; an omitted `max` is unbounded. Enums list their allowed
`values`. Every instance parameter must be declared and type-correct. String
parameters are labels for `title_template`; forms cannot do arithmetic with
them.

### Derived parameters

`derived` supports only `{product: [...]}` and `{sum: [...]}`. Entries in
each list are numeric constants, parameters, or already-resolved derived
names. Derived values are evaluated in YAML declaration order. A derived
name cannot shadow a parameter, and a reference cannot look forward to a
later derived entry. This order is also recorded as `derived_order` in the
normalized model bundle so a JSON consumer does not infer semantic order
from sorted object keys.

### FORM grammar

FORM is deliberately linear; it is the model's only expression language:

```
form := number | estimate |
        {const?: number|estimate,
         per?: {param: number|estimate},
         by?: {enum_param: {value: number|estimate}},
         when?: {enum_param: [value, ...]}}

value(form, params) =
  0, when any `when` predicate does not match; otherwise
  const + sum(per[p] * params[p]) + sum(by[e][params[e]])
```

An omitted term contributes zero. A missing `by` entry for the current enum
value also contributes zero. A list of forms is evaluated left to right and
summed. Lists enable gated alternatives, as in the two boolean branches in
the example. Matching is type-strict: YAML `true` matches boolean `true`,
not the number `1` or the string `"true"`. `when` is valid for enum and
boolean parameters, not free-form strings or numeric parameters.

FORM leaves appear under a kind's `fte_months`, `units`, contract, recurring,
flat amount, duration, and revenue price or annual-volume entries. A revenue
volume vector is a list by year; each vector entry may itself be one form or
a list of forms to sum.

### Kind-backed items and overrides

A menu item names its kind and supplies parameter values:

```yaml
items:
  - id: snap-certified-25
    kind: program-coverage
    params:
      program: SNAP
      jurisdictions: 25
      tier: certified
      qc_data_available: true
      modules_per_jurisdiction: 300
    resourcing:
      fte_months:
        "Encoding Lead": 8
```

Explicit item fields take precedence over kind-derived fields. Resourcing
overrides are deep leaves: the explicit `Encoding Lead` value above replaces
that role only, while other derived roles and units remain. Explicit scalar
leaves replace the corresponding scalar. Explicit duration or revenue
replaces the kind value. Dependencies are the exception: kind-derived and
explicit dependencies are unioned, keeping the first occurrence in
kind-then-item order.

### Presets

`kind_presets` are named, validated starting points for a configurator. They
do not create or cost an item by themselves:

```yaml
kind_presets:
  snap:
    kind: program-coverage
    title: "SNAP"
    params: {program: SNAP, modules_per_jurisdiction: 300}
```

Preset keys must belong to the named kind and values must satisfy its types
and bounds. Presets pass through unchanged in the normalized model bundle.

## selection.yaml — a proposal as a selection over the menu

Schema marker: `schema: grantkit-selection/v1`
(`grantkit-selection/v0` is accepted). One file per proposal.

```yaml
schema: grantkit-selection/v1
id: oaif-2026                  # required; unique across the portfolio
funder: "Example Fund"         # required
status: live                   # required: draft|live|awarded|
                               #           withdrawn|declined
target_usd: 2000000            # optional advisory ask target
window_months: 16              # required integer > 0
horizon_months: 36             # optional; defaults to window_months
org_base:                      # optional fractional org-base claim
  item: org-floor-std          # must resolve; item.type must be
  fraction: 0.10               # org-base; fraction in 0..1
selections:                    # ordered; explicit 0 fractions are
  - {item: pe-parity-full, fraction: 1.0, start_month: 0}
  - {item: abstention-evals, fraction: 0.0,
     note: "declared, not billed here"}         # note optional
notes: "..."                   # optional
```

An explicit `fraction: 0.0` line is a declaration — "this work exists
and this proposal knows about it" — that costs nothing and adds no
personnel rows, but stays visible in the compiled tables.

Each line has an integer `start_month >= 0`, defaulting to zero. A line may
name a menu `item` or carry one private kind `instance`, but never both:

```yaml
selections:
  - instance:
      id: medicaid-certified-12
      kind: program-coverage
      params:
        program: Medicaid
        jurisdictions: 12
        tier: certified
        qc_data_available: true
        modules_per_jurisdiction: 400
    fraction: 1
    start_month: 3
```

An inline instance resolves exactly like a kind-backed item. Its status is
`planned`, and it does not require evidence. Instance ids must be unique
inside the selection and cannot collide with a menu item id. Instances are
private to their selection, so the co-funding (C2) gate does not aggregate
them across proposals. Promote an instance to `menu.yaml` when the work
becomes shared.

## The cost model

All money is carried as floats internally; rendering rounds to whole
dollars (half up) at output. Numeric inputs must be finite. Cost inputs and
`target_usd` must be non-negative; the model has no credit-line convention.

Per item:

```
labor    = sum over roles of fte_months/12 x loaded_usd
units    = sum over units of count x usd_per_unit
other    = sum of duration-costed non_personnel lines
contract = contract_usd + other
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
fit            = total / target_usd        (when target_usd > 0)
```

Two deliberate choices, matching upstream practice:

- **The window does not prorate flat blocks.** An org-base claim is a
  fraction of an item's one-time cost, not a run rate. It does not price that
  item's `recurring_usd_per_year`; recurring is included only when the item
  appears as a regular selection line.
- **Recurring costs on regular selection lines are prorated by the window**
  (`x window/12`) and are overhead-bearing.

## Revenue projections

An explicit item or kind may declare revenue streams. Kind stream prices and
annual-volume entries are FORMs; explicit streams use concrete numbers or
estimate objects.

```yaml
revenue:
  - stream: attested-determinations
    family: B
    unit: "attested determination"
    price_usd:
      {central: 1.0, low: 0.5, high: 1.5, basis: assumed,
       source: "launch posture"}
    volume_per_year: [0, 250000, 1000000]
    starts: completion
    ramp_months: 6
    provenance: ["business-model brief"]
```

`starts` is `start` or `completion` and defaults to `completion`. Item start
is the selection line's `start_month`; completion is start plus resolved
duration (one month when no duration is declared). A zero-duration item's
completion is its start month, so completion-based revenue begins there.
`volume_per_year[0]` is the annual rate for the stream's first twelve months,
index 1 for the next twelve, and so on. The last value persists for every
later year. Revenue is projected through `horizon_months`, in periods measured
from the selection's start.

When `ramp_months` is present, the stream's rate rises linearly from zero to
full rate over that interval. The compiler integrates the ramp over continuous
month overlaps; it does not round a start, completion, or ramp to a whole
month. Price times annual volume is divided across the relevant months before
period aggregation.

Two totals make attribution explicit:

- `enabled_usd` is the full projected stream for a line whose fraction is
  greater than zero.
- `attributed_usd` is enabled revenue multiplied by that line's fraction.

The compiled output reports both by stream and period, never silently nets
one against cost, and separately reports
`net_of_attributed_usd = total_usd - attributed_total`. Attribution is a
convention, not an accounting conclusion. These streams are org-level
projections and the budget model is not a P&L.

## Phasing and staffing

GrantKit emits twelve-month periods from selection month zero. The period
extent is the latest of the cost window, revenue horizon, and the end of any
scheduled non-recurring work. The last period may therefore contain fewer
than twelve months.

Labor, units, contract, and flat item costs are spread uniformly over each
line's `[start_month, start_month + duration_months)` interval. Unlike the
selection total, recurring cost is a run rate: it is spread over the cost
window only. A flat org-base block keeps the v0 arithmetic and is spread
uniformly over the window for reporting. An explicit `duration_months: 0` is
the compatibility exception: the item is instantaneous, and all of its
one-time cost is assigned to the period containing `start_month`; on an annual
boundary, that is the period beginning there. Org bases start at month zero. A
roster entry without its own `months` and an itemized `usd_per_year`
non-personnel line both use the zero duration and therefore contribute zero.
An itemized `usd_total` remains the stated total and is assigned to the
instantaneous period; recurring cost remains a window run rate.

Scheduled work may extend beyond `window_months`. Those dollars remain in the
later periods rather than disappearing, and `outside_window_usd` separately
reports the portion beyond the window, including its associated overhead.
For a `grantkit-selection/v1` document, more than USD 1 produces the advisory
`phase_outside_window` warning. Legacy v0 selections receive the same phased
data but retain their v0 gate output. This reconciles two invariants: the v0
total is window-independent except for recurring cost, and the sum of period
category totals equals the compiled selection total to `1e-6`.

Each period reports cost by category plus two staffing maps:

- `fte_by_role` is incremental FTE, computed as fraction-weighted FTE-months
  in the period divided by the period's months.
- `base_fte_by_role` is roster FTE from the selected org base.

### Bottoms-up org bases

An org-base item can derive its complete pre-fee cost from a roster and
itemized non-personnel lines instead of inheriting a published lump:

```yaml
duration_months: 36
resourcing:
  roster:
    - {role: "Encoding Lead", fte: 1.0}            # 36 seat-months
    - {role: "Encoding Lead", fte: 0.5, months: 24} # 12 seat-months
    - {role: "Operations Manager", fte: 0.5}
  non_personnel:
    - label: "AI seats"
      usd_per_year: 24000
      basis: configured
      source: "floor-bottoms-up.ts:FLOOR-STD"
    - label: "Corpus acquisition"
      usd_total: 75000
      basis: computed
      source: "floor-bottoms-up.ts:FLOOR-STD"
```

Roster roles may repeat. Each entry is costed independently as
`fte * months / 12 * loaded_usd`; a line without `months` uses the item's
duration. This makes a source model's ramp exact in seat-months instead of
collapsing it to one inherited personnel total. Period staffing and the
capacity gate sum every active entry for the role. As in v0.4, roster entries
start at the beginning of the org-base item.

Every `non_personnel` entry has a non-empty label that is unique within the
item and exactly one of:

- `usd_total`: the complete amount over the item duration; or
- `usd_per_year`: an annual rate, multiplied by `duration_months / 12`.

Amounts must be finite and non-negative. Optional `basis` is `computed`,
`configured`, or `assumed`; optional `source` identifies the source-model
line. Compiled item JSON reports each duration-costed line as
`{label, usd, basis, source}`. Compiled selection JSON repeats the lines under
`org_base.non_personnel`, with `usd` scaled by the selection's org-base
fraction, so a surface can render the selected share's other-cost table.

Bottoms-up roster labor and non-personnel bear the selection-level fee because
a fully bottoms-up base does not set `overhead_included`. The flag retains its
v0.4 meaning for existing fee-inclusive blocks, including roster and
non-personnel components. The legacy `non_personnel_usd_per_year` lump remains
readable but cannot be mixed with the itemized list. Flat `amount_usd` blocks
also remain compatible. If `amount_usd` and a roster appear together, their
costs are additive exactly as in v0.4; the roster is never informational.

Reconciliation is a checked property, not a cost input. Compile the roster
and itemized lines, compare the resulting item `one_time_usd` with the source
model's published **pre-fee** total, and report the residual. Never absorb a
residual by changing a rate, adding a plug line, or copying the target into
`amount_usd`. Once the pre-fee base reconciles, the selection's fee emerges
from the normal overhead formula.

The selection's org-base fraction scales the dollars attributed to that
funder. It does not scale `base_fte_by_role`: the org and its people exist in
full, while the fraction is only the funder's share.

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
| `kind_unknown` | An item or inline instance names a missing kind. |
| `kind_param_invalid` | Kind, preset, or instance parameters are missing, undeclared, out of bounds, or have the wrong type. |
| `kind_form_invalid` | A FORM has bad grammar, a bad reference, or an invalid `when`. |
| `derived_invalid` | A derived expression is invalid, shadows a parameter, or references a value before it is available. |
| `estimate_invalid` | An estimate is non-finite, negative, misordered, or has an invalid basis. |
| `instance_id_collision` | An inline id repeats in its selection or collides with a menu id. |
| `revenue_invalid` | A stream has a negative price or volume, or an invalid `starts` value. |
| `budget_non_finite` | Individually valid finite inputs overflowed the compiler's finite numeric range; reduce their magnitudes. |
| `budget_currency_mismatch` | Bound rule pack only: the portfolio and the funder's caps use different currencies, so cap checks cannot run. |
| `budget_over_total_cap` | Bound rule pack only: the compiled total exceeds the funder's published total cap. |

Warnings (advisory heuristics, clearly labeled — not funder rules):

| Rule | Meaning |
|------|---------|
| `dependency_unfunded` | A funded regular or `org_base` item depends on `planned` work that no live/awarded selection (nor this one) funds. |
| `over_target` | The compiled total exceeds the advisory `target_usd` (a target is an ask, not a cap). |
| `load_factor_suspicious` / `components_mismatch` | Rates heuristics — see [the rates contract](rates-contract.md). |
| `phase_outside_window` | More than USD 1 of scheduled cost falls beyond the selection's cost window; the dollars remain in totals and periods. |
| `role_over_allocated` | Incremental plus org-base FTE exceeds a role's declared capacity for a period. |
| `budget_over_annual_cap` | Bound rule pack only: total x 12/window_months exceeds the funder's annual cap. A uniform-spread approximation, hence a warning — confirm against your actual phasing. |

### The co-funding gate

For each menu item, the fractions across all selections with status
`live` or `awarded` — including `org_base` fractions — must sum to at
most 1 (tolerance 1e-9, so two exact halves pass). The finding lists
every contributing selection and its fraction.

Inline instances are deliberately excluded. They are private to one
selection and cannot represent a shared menu claim.

`draft`, `withdrawn`, and `declined` selections are excluded: drafts
are free to over-plan. The invariant binds simultaneous live
applications, and the gate fires the moment an over-planned draft goes
live.

### The role-capacity gate

A rate may declare `capacity_fte`. For each role and period, GrantKit sums
incremental FTE across every `live` or `awarded` selection. An org-base
item's unscaled roster FTE counts once even when several selections reference
that same item: their fractions claim funding shares in one organization,
not duplicate staff. Distinct org-base items count separately. When compiling
a non-binding selection directly, that selection is added to the live/awarded
set as a scenario. An unscoped portfolio check does not add every draft.

`role_over_allocated` warns when demand is greater than
`capacity_fte * 1.0000001`; the small relative tolerance keeps floating-point
noise at the boundary quiet. The message names the role, period, demand,
capacity, and contributing selections. Capacity is an advisory planning
constraint, not a funder rule, so it never blocks compilation.

## Combining packages

Several proposal packages can be viewed as one funding scenario without
rewriting any of their honest asks:

```bash
grantkit budget org-portfolio \
  --combine ballmer-l1,oaif-2026,pbif-2026,state-contract-az \
  --json
grantkit budget org-portfolio \
  --combine ballmer-l1,oaif-2026 \
  --output combined.md
```

`--combine` requires at least two distinct selection ids and either `--json`,
`--output`, or both. The ids are sorted before compilation, so input order
does not affect the bytes. It does not accept `--selection`, `--all`,
`--check`, `--export-model`, `--narrative`, or `--periods`; phasing and
staffing are already part of every combined artifact.

The rollup stacks each funder's fraction and funded dollars per shared menu
item, then reports the sum. This is the C2 ledger read positively: a sum of
75% says the selected packages fund 75% of that item. A sum above 100% is
still the existing `cofunding_over_allocated` error and remains visible in
the combined gates. The compiler does not lower, rebalance, or hide either
ask.

Each referenced `org-base` item also gets a funding-coverage ledger. The
selected fractions are funder segments, and `max(0, 1 - sum(fractions))` is
an explicit **Unclaimed** gap segment. That gap is the honest expectation
that other funders cover the rest, not a zero-cost assumption. At exactly
100% the explicit gap remains present at 0%. At more than 100%, the gap is
zero and C2 reports the over-allocation.

Coverage uses the same item ledger as C2, including an `org-base` menu item
claimed as an ordinary selection line. Each JSON share retains
`claim_kind: item | org_base | gap`, so consumers can show how the claim was
declared without inventing a gap or splitting one item into two ledgers.

Combined category and period costs sum the selected asks. Funded personnel
likewise sums each selection's fraction-weighted attribution. Operational
staffing has different semantics: incremental FTE sums, but a roster on the
same org-base item is counted once no matter how many funders claim shares
of it or whether a share uses an ordinary item line or `org_base`. Different
org-base items remain different organizations and add.

Revenue is grouped by shared item, stream, schedule, and assumptions.
Enabled revenue for the identical shared stream is counted once (the maximum
in each period); attributed revenue stacks by funded fraction. The JSON
includes each funder's stream share as well as combined period and lifetime
totals.

For this scenario every selected proposal is treated as live, including a
proposal whose file says `draft`; unselected proposals do not participate.
Computable C2 errors are embedded in the JSON/Markdown gates and do not
suppress the rollup, because resolving that funding decision is the point of
the view. Structural errors still block compilation. Single-selection
compilation is unchanged and remains the funder-only view.

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

A broken binding is itself a check error: `budget_model_invalid` (the
block is not a mapping or has invalid `portfolio` / `selection` values),
`budget_model_unreadable` (the portfolio directory will not load), or
`unknown_selection` (the bound id is not in the portfolio).

## The budget verb

```
grantkit budget [PATH]
  --selection TEXT   selection id to compile, or an optional scope for
                     --check; required to compile a multi-selection
                     portfolio unless PATH binds one
  --all              compile every selection (requires --json)
  --combine IDS      combine two or more comma-separated selection ids;
                     requires --json and/or --output
  --check            run the gates only; exit 1 on findings that are
                     errors, 2 on selection/configuration/loading failures
  --json             emit the full structured compilation as JSON
                     (with --check, the gate findings)
  --export-model PATH
                     write a normalized grantkit-model/v1 bundle
  --output PATH      write the markdown budget document to a file
  --narrative        include the narrative skeleton in the markdown
                     (without --output, prints the markdown document)
  --periods          include phased cost and staffing tables in Rich or
                     Markdown output (JSON always includes periods)
```

Warnings do not make `budget --check` fail; `--strict` belongs to the proposal
`check` verb and is not a budget option. `--output` and `--narrative` cannot be
combined with `--check`. With `--json`, `--narrative` requires `--output`, so
the JSON stays alone on stdout while the narrative goes to the markdown file.
If single-selection/`--all` compilation, or a combined scenario with a
structural error, is blocked by gates, `--json` emits the structured findings
instead of a compiled budget. A computable combined C2 conflict stays inside
the rollup as described in [Combining packages](#combining-packages).

`--all --json` is the cross-implementation conformance output:

```json
{"selections": {"funder-a": {}, "funder-b": {}}}
```

Each value is the same full compilation returned by a single-selection JSON
run. Selection ids are sorted. `--all` does not need or accept a selected id,
and it can compile an empty portfolio to an empty `selections` mapping.

`--combine --json` emits `grantkit-combined-budget/v1`: canonical selection
ids, per-funder totals, item funding stacks, org-base coverage and gap
segments, combined categories, base-once staffing, revenue, and the scenario
gate result. Mapping keys and all id-addressed arrays are deterministic.

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

When `--periods` is set, Rich and Markdown outputs add a Phasing table and a
Staffing table with incremental and base FTE. Revenue projections add enabled
and attributed tables and the attribution disclaimer. Structured JSON always
contains periods and revenue, regardless of this presentation flag. The
narrative adds a `Revenue enabled` line for an item with streams.

### The normalized model bundle

`--export-model model.json` writes the complete, validated input needed by a
separate compiler or configurator:

```text
schema: grantkit-model/v1
generated_from: menu/rates schemas, provider, generated date, rates scenario
currency, overheads
unit_costs: central values plus estimate metadata
kinds, kind_presets
items: raw definitions plus concrete resolved definitions
rates: normalized role records
selections: raw selection documents
```

Kind definitions otherwise remain verbatim. Each exported kind also has a
`derived_order` sibling listing its derived names in source declaration order.
A consumer must use that list rather than sorted JSON object order when it
evaluates derived expressions.

The exporter sorts mapping keys and id-addressed collections, uses two-space
JSON indentation, and writes one trailing newline. `--all --json` likewise
sorts selection ids. Neither output contains a wall-clock generation time or
another volatile value, so identical inputs produce byte-identical files.
All arithmetic remains IEEE-754 double precision with no intermediate
rounding; whole-dollar half-up rounding belongs only to human rendering.

## Scope

Still out of scope: currency conversion (a menu/rates mismatch is a
validation error, and a portfolio/funder-cap mismatch is a
`budget_currency_mismatch` error), emitting a legacy NSF-category
`budget.yaml` from a selection, BLS validation of menu roles (the existing
salary validator remains `budget.yaml`-only), and uncertainty sampling. V1
retains estimate metadata so sampling can be added without another schema
migration.
