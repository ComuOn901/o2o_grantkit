# Adversarial findings triage and review r1

Date: 2026-08-15

Branch: `feat/budget-model`

Scope: GrantKit v0.3 menu/rates/selection budget model

## Outcome

All 39 supplied findings were verified against the current tree. Real defects
and documentation gaps were fixed; duplicate, already-resolved, and
spec-incompatible findings are identified below. A second hostile review then
found and fixed additional schema, YAML, arithmetic, rendering, binding, and
error-handling defects.

**Hard-stop integration check: passed.** The Axiom `oaif-2026` compiled total
is still `2578998.5666666664` (`2578998.57` to cents), its fit is still
`128.949928333333%`, and an unscoped `budget --check --json` exits 0 with
0 errors and 6 warnings. `anthropic-bd` remains at `88.102835555556%` fit.

## Part 1: supplied finding dispositions

| # | Finding | Disposition |
|---:|---|---|
| 1 | NaN passes gates and poisons JSON | **Fixed** in `02ce59f`; all parsed menu/rates/selection numeric fields reject non-finite values. Pack numeric validation and derived-overflow follow-through landed in `3393234`. |
| 2 | `target_usd: 0` raises `ZeroDivisionError` | **Fixed** in `02ce59f`; zero is a valid target value but produces no fit or over-target division. |
| 3 | Scoped C2 can be offset by invalid out-of-scope fractions | **Fixed** in `02ce59f`; fraction range validation is portfolio-wide before scoped selection gates. |
| 4 | `budget --check --selection <unknown>` exits 0 | **Fixed** in `5bd875f`; the CLI now exits 2 with the available ids. |
| 5 | Negative dollar fields compile negative totals | **Fixed** in `02ce59f`; unit prices, resourcing money, and targets are non-negative. The remaining `components[*].amount_usd` spelling was covered in `3393234`. |
| 6 | Recursive dependency DFS fails on deep chains | **Fixed** in `02ce59f`; cycle detection uses an explicit iterative stack. Random-graph comparison and 10,000-node probes found no misses or recursion failure. |
| 7 | Unknown-key tolerance makes typos silent | **Fixed as a documentation finding** in `f53da71`; v0 intentionally tolerates producer extensions, and the docs now explicitly warn that unknown keys are ignored, especially a misspelled `overhead_included`. |
| 8 | Org-base claims omit `recurring_usd_per_year` | **Fixed as a documentation finding** in `f53da71`; the authoritative formula prices an org-base claim from one-time cost only, while a regular selection line prices recurring cost. The exclusion is now explicit. |
| 9 | `selections/*.yml` is not discovered | **Rejected.** The authoritative contract specifies `selections/*.yaml` and a single root `selection.yaml`. Expanding the discovery surface would diverge from it. The zero-selection diagnostic now names the supported paths. |
| 10 | Missing output parent produces traceback | **Fixed** in `5bd875f`; write failures are clean exit-2 diagnostics. |
| 11 | Empty portfolio says to pass an impossible id | **Fixed** in `5bd875f`; the message says the portfolio has no selections and names both supported layouts. |
| 12 | An unrelated invalid draft blocks compilation | **Rejected.** A portfolio is one integrity unit: schema errors short-circuit structural gates, while “drafts are free to over-plan” applies only to C2 allocation. Compiling an artifact from a known-invalid portfolio remains intentionally disallowed. |
| 13 | eggnest-employer contract documentation | **Already fixed** in `08e7eb6`; current exported rates validate with zero errors. |
| 14 | Docs index still said five verbs | **Already fixed** in `cdb1033`. |
| 15 | C2 docs omitted `awarded` selections | **Already fixed** in `cdb1033`. |
| 16 | Docs omitted `--check --json` findings output | **Already fixed** in `cdb1033`. |
| 17 | Binding-failure rule ids undocumented | **Already fixed** in `cdb1033`. |
| 18 | README described every path as a grant directory | **Already fixed** in `cdb1033`. |
| 19 | CLI overview omitted budget exit semantics | **Already fixed** in `cdb1033`. |
| 20 | Programmatic menu API omitted | **Already fixed** in `cdb1033`. |
| 21 | Missing bound selection prints Python `None` | **Fixed** in `5bd875f`; the message now asks for `selection: <id>` and lists available ids. |
| 22 | Concurrent loader/render tests were untracked | **Already fixed** in `490494c`; both files and their coverage are tracked. |
| 23 | Duplicate unknown-id `--check` finding | **Fixed** with finding 4 in `5bd875f`. |
| 24 | `--json --output` pollutes stdout | **Fixed** in `5bd875f`; JSON is alone on stdout and write confirmation goes to stderr. |
| 25 | Gate-blocked `--json` prints a Rich table | **Fixed** in `5bd875f`; it emits the structured `CheckResult` JSON and exits 1. |
| 26 | Pack cap compares mismatched currencies | **Fixed** for the selection model in `02ce59f`; `budget_currency_mismatch` is an error and the incommensurable comparison is skipped. The legacy `budget.yaml` contract has no declared budget currency to compare, so no unsupported inference was added there. |
| 27 | Portfolio-wide errors block an otherwise computable selection | **Rejected.** Compilation intentionally refuses every artifact while the portfolio has integrity errors; `--check` remains the diagnostic surface. An override would weaken the compiler contract and needs a separate design decision. |
| 28 | Budget lacks a `--strict` analogue | **Fixed as a contract clarification** in `f53da71`; warnings do not fail `budget --check`, and `--strict` belongs only to proposal `check`. |
| 29 | Duplicate missing-selection `None` message | **Fixed** with finding 21 in `5bd875f`. |
| 30 | Contradictory flags are silently ignored | **Fixed** in `5bd875f`; `--check` rejects output/narrative, and JSON+narrative requires a Markdown output path. |
| 31 | `.yml` invisibility yields an unhelpful error | **Fixed diagnostically** in `5bd875f`; the no-selection message identifies `selections/*.yaml` and root `selection.yaml`. Loading `.yml` remains rejected for the finding-9 reason. |
| 32 | Second duplicate unknown-id `--check` finding | **Fixed** with finding 4 in `5bd875f`. |
| 33 | Duplicate JSON/output stdout pollution | **Fixed** with finding 24 in `5bd875f`. |
| 34 | Loader error-path coverage | **Already fixed** in `490494c`. |
| 35 | Renderer branch coverage | **Already fixed** in `490494c`. |
| 36 | Schema negative-case coverage | **Already fixed** in `490494c`, then extended in `02ce59f` and `3393234`. |
| 37 | Engine edge-semantics coverage | **Already fixed** in `490494c`, then extended in `3393234`. |
| 38 | Gate edge coverage | **Already fixed** in `490494c`, then extended in `02ce59f` and `3393234`. |
| 39 | CLI path coverage | **Already fixed** in `490494c`, then extended in `5bd875f` and `3393234`. |

## Part 2: fresh hostile review

### Applied

All code and regression tests in this section landed in `3393234`; associated
contract and CLI documentation landed in `2ef1968`.

- Hardened every documented menu/rates/selection string, string-list, and
  mapping-key shape before dataclass parsing. Unsafe control text, lone Unicode
  surrogates, unhashable enum values, and unrepresentably large integer inputs
  now produce findings rather than tracebacks or lossy coercion.
- Hardened funder-pack known-field shapes and rejected non-finite pack budget
  rules. Random leaf-shape mutation of all four validators produced no crash.
- Added a SafeLoader-derived strict portfolio loader that rejects duplicate
  keys while preserving standard YAML aliases and merge-key overrides. It also
  normalizes invalid UTF-8, unreadable paths, excessive nesting, and leaked
  PyYAML constructor exceptions into `PortfolioError`. Unsafe Python tags
  remain rejected.
- Rejected a reserved `selections` path that exists but is not a directory and
  made the documented `load_portfolio(str | Path)` API actually accept strings.
- Detected arithmetic overflow and underflow-derived non-finite values after
  compilation. `budget_non_finite` blocks compile and remains valid JSON; no
  `NaN` or `Infinity` numeric literal can escape through the CLI.
- Reordered recurring arithmetic to avoid an unnecessary intermediate float
  overflow and used Decimal only at rendering/gate boundaries where it avoids
  false overflow or inconsistent rounding without changing the float engine.
- Centralized half-up money formatting, made it work for very large finite
  values, and made percentages precise enough not to round real violations
  away (`7.5%`, `100.1%`, and tolerance-scale C2 diagnostics remain truthful).
- Removed Rich-markup interpretation of portfolio content, escaped hostile
  terminal controls, escaped Markdown table pipes/newlines, and kept intended
  narrative Markdown literal rather than re-evaluating it through Jinja.
- Included fraction-weighted org-base labor in the personnel view. Org-base
  dependencies now count as funded where appropriate and are themselves
  checked for unfunded prerequisites. Compiled category totals are unchanged.
- Made malformed, non-mapping, unreadable, or structurally hostile
  `grant.yaml` files clean exit-2 configuration errors across proposal and
  bound-budget CLI paths. Malformed `budget_model` values can no longer
  silently disable checking or escape as raw exceptions.
- Corrected binding auto-selection, terminal help, annual-cap severity docs,
  deterministic-output wording, and the documented `budget_non_finite` rule.

Independent adversarial verification covered 100,000 valid extreme-numeric
portfolio cases, random schema leaf mutations, and randomized dependency
graphs. It found no remaining crash, non-finite JSON leak, or cycle miss.

### Recommended only / judgment calls not applied

- **Bound selection override and pack:** `budget GRANT --selection other-id`
  retains the grant project's funder pack. Decide whether to reject the
  override, suppress the pack when ids differ, or explicitly bless this.
- **Dual budget models:** a project containing both legacy `budget.yaml` and
  `budget_model` runs both systems. Define precedence or document intentional
  dual checking before adding a consistency rule.
- **Path marker precedence:** a directory containing both `grant.yaml` and
  portfolio markers is treated as a grant project. This is deterministic but
  should be documented if mixed directories are expected.
- **Additional economic bounds:** the design requires type validation, but
  does not unambiguously require positive `base_usd`, non-negative benchmark
  values, or a benchmark percentile in `0..100`. Recommend adopting those
  semantic bounds in the next schema revision rather than inventing them here.
- **Displayed reconciliation:** independently rounded personnel/category rows
  can differ from the rounded total by a small residual. Define a residual-line
  policy only if exact displayed reconciliation is a requirement.
- **Diagnostics:** selection source filenames, explicit org-base identity, and
  deduplication of repeated dependency warnings would improve usability but do
  not justify restructuring sound arithmetic.
- **Content boundary:** narrative `what` and `evidence` deliberately remain
  trusted local Markdown. If GrantKit later accepts untrusted remote content,
  sanitize at the HTML boundary rather than escaping the Markdown compiler.
- **YAML consistency:** all reviewed loaders use `yaml.safe_load` or a
  `SafeLoader` subclass, but duplicate-key rejection is currently specific to
  the new portfolio loader. A future shared strict loader could cover legacy
  grant, pack, and budget YAML without changing this release's compatibility.
- **Discovery and compile policy:** retain `.yaml`-only selection discovery
  and atomic refusal to compile an invalid portfolio unless the authoritative
  design explicitly changes those contracts.

## Test modifications and justification

No test was weakened or deleted.

- The one strict xfail from `490494c` (unknown selection under
  `budget --check`) was removed after the defect was fixed; it now asserts the
  exact exit-2 contract and actionable message.
- Loose output assertions were strengthened to parse JSON, verify stderr/stdout
  separation, and assert exact error rules.
- The former “JSON takes precedence over narrative” expectation encoded silent
  option dropping. It was replaced by one test for the usage error and one test
  proving JSON plus an explicit narrative output are both honored.
- The empty-portfolio assertion changed from checking `(none)` to checking the
  actionable supported-path message.
- Percentage expectations changed from misleading integer rounding (`49%`) to
  the truthful bounded representation (`49.01%`), and deterministic wording
  assertions were updated to distinguish compiled documents from adaptive
  terminal layout.
- All other test changes add regression coverage for newly fixed defects and
  adversarial boundaries.

## Final verification

- `pytest -q`: **577 passed, 1 skipped**.
- `ruff check .`: **clean**.
- `black --check .`: **clean** (70 files unchanged).
- Mypy on all touched source modules with normal imported-module suppression:
  **clean, 10 source files**.
- Repository-wide `mypy grantkit`: **60 legacy errors in 15 files**, down from
  the 68-error starting baseline; no error is in a touched source module. Mypy
  remains non-fatal in repository CI as documented.
- Axiom exact compile command: exit 0,
  `total_usd=2578998.5666666664`, rounded `2578998.57`,
  fit `128.949928333333%`.
- Axiom unscoped `--check --json`: exit 0, 0 errors, 6 warnings.
- Axiom `anthropic-bd`: exit 0, `total_usd=1057234.0266666666`,
  fit `88.102835555556%`.

## Fix/review commits

- `08e7eb6` — rates-contract precision (already present).
- `cdb1033` — budget documentation precision (already present).
- `490494c` — adversarial coverage pass (already present).
- `02ce59f` — budget integrity gates and schema hardening.
- `5bd875f` — CLI output, selection, and option contracts.
- `f53da71` — validation-contract documentation.
- `3393234` — Part-2 adversarial portfolio, arithmetic, YAML, and rendering
  hardening.
- `2ef1968` — Part-2 hardened-contract documentation.

No commit was pushed.
