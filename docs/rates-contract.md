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

Schema marker: `schema: grantkit-rates/v0`.

```yaml
schema: grantkit-rates/v0
provider: "eggnest-employer 0.2.0"   # generator + version (required)
generated: "2026-08-15"              # ISO date (required)
scenario: "axiom-foundation-2026"    # provider-side scenario id (optional)
currency: USD                        # required; must match the menu
jurisdiction: "US-NY"                # optional
method: >-                           # optional prose derivation
  Loaded cost = base + employer payroll taxes (computed from encoded
  law via policyengine) + employer retirement contribution (rate x
  base, capped) + configured benefits schedule.
roles:
  - role: "Encoding Lead"            # required; referenced by the
                                     # menu's fte_months; unique
    loaded_usd: 320000               # required: annual fully-loaded
                                     # cost, > 0
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
        source: "25% x base, IRC 415(c) cap"
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
- **Basis vocabulary**: every component's `basis` is exactly one of
  `computed` (derived from encoded rules or data), `configured` (a
  scenario input someone chose), or `assumed` (a placeholder guess).
  The point is honesty about provenance: a reviewer can see at a
  glance which dollars trace to law and which to assumption.
- **Single currency**: the rates currency must match the menu currency;
  a mismatch is a validation error (GrantKit does not convert).
- **Provider identity**: `provider` and `generated` appear verbatim in
  every compiled budget's generated-from line, so a budget is always
  traceable to the exact rates snapshot that produced it. Regenerate
  the file rather than editing it by hand.

## Advisory heuristics

`grantkit budget --check` runs two warnings over the rates. Both are
GrantKit's own heuristics — documented sanity checks, not funder rules —
and both need `base_usd` to be present:

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
6. Test your numbers in your own suite. GrantKit will not re-derive
   them, by design.
