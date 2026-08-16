# The rates contract

`rates.yaml` answers one question for the [budget model](budget-model.md):
what does a year of each role actually cost, fully loaded? GrantKit does
not compute that answer — a **rates provider** does. The contract splits
the work cleanly:

- **The provider** computes loaded costs (base salary, employer taxes,
  retirement, benefits) however it likes, and emits a `rates.yaml`
  declaring what it computed, how, and from what sources.
- **GrantKit** validates the file's structure, uses the loaded rates in
  compilation, and runs a couple of advisory sanity heuristics. It never
  recomputes the provider's law-based numbers — that is the provider's
  job, covered by the provider's tests.

The reference provider is **eggnest-employer**, which computes employer
payroll taxes from encoded law (via policyengine) plus a configured
retirement and benefits schedule, and emits this format directly.

## The file

Schema marker: `schema: grantkit-rates/v1`. GrantKit also accepts every
`grantkit-rates/v0` file; `capacity_fte` is optional, so upgrading the marker
does not change an existing portfolio's arithmetic.

```yaml
schema: grantkit-rates/v1
provider: "eggnest-employer 0.2.0"   # generator + version (required)
generated: "2026-08-15"              # ISO date (required)
scenario: "axiom-foundation-2026"    # provider-side scenario id (optional)
currency: USD                        # required; must match the menu
jurisdiction: "US-NY"                # optional; omit when roles span
                                     # jurisdictions or none is set
method: >-                           # optional prose derivation
  Loaded cost = base + employer payroll taxes (computed from encoded
  law via policyengine) + employer retirement contribution (rate x
  base, capped) + configured benefits schedule.
roles:
  - role: "Encoding Lead"            # required; referenced by the
                                     # menu's fte_months; unique
    loaded_usd: 320000               # required: annual fully-loaded
                                     # cost, > 0
    capacity_fte: 1.0                # optional available headcount
    base_usd: 240000                 # recommended: annual base salary
    soc: "15-1252"                   # optional SOC code
    components:                      # optional breakdown
      - name: employer_taxes
        amount_usd: 18000
        basis: computed              # required per component
        source: "policyengine-us 1.x"
      - name: retirement
        amount_usd: 47500
        basis: computed
        source: "25% x base, 415(c) cap from policyengine parameters"
      - name: benefits
        amount_usd: 14500
        basis: configured
        source: "scenario benefit schedule"
    benchmark:                       # optional market provenance
      source: "BLS OEWS May 2024, SOC 15-1252, national"
      percentile: 75
      value_usd: 130560
    provenance: ["..."]              # optional source strings
```

## Contract rules

- **Required keys**: `schema`, `provider`, `generated` (an ISO date),
  `currency`, and `roles`. Each role requires `role` (unique) and a
  positive `loaded_usd`.
- **Capacity is optional**: `capacity_fte`, when present, is a finite,
  non-negative number. It is available headcount for planning, not a salary
  component, funding fraction, estimate object, or funder limit. Zero is a
  meaningful declaration that no current capacity is available.
- **Basis vocabulary**: every component's `basis` is exactly one of
  `computed` (derived from encoded rules or data), `configured` (a
  scenario input someone chose), or `assumed` (a placeholder guess).
  The point is honesty about provenance: a reviewer can see at a
  glance which dollars trace to law and which to assumption. The basis
  names where the binding number came from, not whether arithmetic
  ran: the reference provider labels retirement `configured` when the
  scenario fixes the amount or supplies a manual cap, and `computed`
  only when the cap is resolved from policyengine parameters.
- **Unknown keys are tolerated**: validation checks the keys named
  here and ignores anything else, at every level of the file, so
  providers may carry extra keys. The reference provider adds
  `benchmark.org_percentile` — where the org's package lands on the
  market curve, in the same percent units as the sibling `percentile`
  — and, on degraded roles, a role-level `notes` string. Such a file
  still validates cleanly; GrantKit never renders keys it does not
  know.
- **`method` is the honesty surface**: the paragraph should state what
  loaded cost includes *and excludes* (the reference provider names
  bonus, equity, and health benefits as excluded), and any fallback
  taken during generation — roles whose employer taxes could not be
  computed, tax variables unavailable in the environment — must be
  stated there too.
- **Single currency**: the rates currency must match the menu currency;
  a mismatch is a validation error (GrantKit does not convert).
- **Provider identity**: `provider` and `generated` appear verbatim in
  every compiled budget's generated-from line, so a budget is always
  traceable to the exact rates snapshot that produced it. Regenerate
  the file rather than editing it by hand.

## Advisory heuristics

`grantkit budget --check` runs two reconciliation warnings over rate data.
Both are GrantKit's own heuristics — documented sanity checks, not funder
rules — and both need `base_usd` to be present:

- `load_factor_suspicious` — `loaded_usd / base_usd` below 1.05 or
  above 2.0. The low side catches a real bug class found in the wild:
  a base salary pasted into the loaded column (three roles in one seed
  file). The high side catches the reverse confusion.
- `components_mismatch` — components are present but
  `base_usd + sum(components)` differs from `loaded_usd` by more than
  one dollar. The breakdown should reconcile with the total it claims
  to explain.

A loaded-only role (no `base_usd`) is valid and triggers neither
heuristic.

### Capacity warning

`capacity_fte` enables the portfolio-level `role_over_allocated` warning.
For each role and twelve-month period, GrantKit sums incremental FTE and the
unscaled roster FTE of referenced org bases across all `live` and `awarded`
selections. When a draft, withdrawn, or declined selection is compiled
directly, that selection is added to the binding set as a planning scenario.
An unscoped portfolio check considers only live and awarded selections.

The gate warns only when demand is greater than
`capacity_fte * 1.0000001`. Its message reports the role, period, demand,
capacity, and contributing selections. Equality, including the relative
tolerance, passes. The warning is advisory and does not change costs or block
compilation.

## Writing your own provider

Any tool that emits the format above is a rates provider — a script
over your payroll export works. Guidelines:

1. Emit, don't hand-edit: make the file a build artifact of your
   scenario inputs, and bump `generated` on every run.
2. Set `provider` to a name and version a reader can chase down.
3. Include `base_usd` and `components` when you can — they unlock the
   reconciliation heuristics and make review far easier.
4. Label every component's `basis` honestly; `assumed` is a fine
   answer and much better than a silent guess.
5. Add `benchmark` blocks where you have market data (e.g. BLS OEWS by
   SOC code); the compiled personnel table and narrative skeleton cite
   them verbatim.
6. Add `capacity_fte` only when the organization can defend an available
   headcount. It is a planning decision and should not be inferred from a
   salary or a proposal's funding share.
7. Test your numbers in your own suite. GrantKit will not re-derive
   them, by design.
8. Never degrade silently — recommended conduct for every provider.
   When part of the computation is unavailable (a role with no
   employer tax state; tax variables missing from the installed
   environment), emit the number you can stand behind, say exactly
   what is missing, and raise a visible warning at generation time.
   The reference provider does all three: `loaded_usd` falls back to
   the guaranteed package total, the role carries a `notes` string
   saying employer taxes were not computed, `method` records the
   fallback, and generation emits a runtime warning.
