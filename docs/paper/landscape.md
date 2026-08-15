# Landscape: prior art for the "Grants as code" claims

Evidence file for `grants-as-code.qmd`. Compiled 2026-08-14 by web sweep
(vendor docs, help centers, federal guidance; marketing claims discounted where
docs said less). Adversarial stance: each entry states which claim (C1–C6) it
touches and whether it weakens it. Absence-of-evidence caveat: sweeps were
US-centric and English-language; a claim marked NOVEL means *no prior art
found*, not *proven absent*.

Claims under test (abbreviated; full statements in the paper):

- **C1** Budgets as compiled artifacts (priced work-item menu → pure-function budget, reproducible in CI).
- **C2** Pre-award cross-application double-billing gate (per-item co-funding fractions across simultaneous proposals must sum ≤ 1, machine-checked).
- **C3** Rule-derived personnel rates (loaded cost from encoded tax/retirement law, with benchmark provenance).
- **C4** Funder-as-view (one org work substrate; N proposals as selections with co-funding fractions).
- **C5** Versioned funder packs (form rules + budget caps as code; CI-validated applications emitting a status artifact).
- **C6** Funder-facing configurator over the org's own live cost model.

---

## 1. Grant-writing and application tools (nonprofit side)

The lane question: does any of these derive budgets from structured work-item
data, or do they only draft narrative text? **Finding: narrative text (and
post-award tracking). None compiles a budget from a structured work-item
substrate.** The closest thing to "budget generation" in this lane is an LLM
writing a budget-shaped table as prose.

- **Instrumentl** — Instrumentl, Inc. Grant discovery + tracker + post-award
  management. Its budget feature is *Budget Spenddown Tracking*: drag-and-drop
  an award budget, extract funder-approved categories, sync actuals from
  accounting, alert on over/under-spend. Post-award, expense-side; nothing
  compiles a proposal budget from work items. Paid SaaS (tiered plans;
  spenddown gated to Professional/Advanced).
  <https://www.instrumentl.com/product-overview>,
  <https://help.instrumentl.com/en/articles/9114092-budget-spenddown-tracking>.
  Verdict: touches C1 only as contrast — budget-as-tracked-spreadsheet, not
  budget-as-compiled-artifact.
- **Grantable** — Grantable Co. AI drafting over a content library ("write
  once, reuse"): upload an RFP, generate structured narrative responses;
  in-line AI editing. Free tier / ~$50–150 per month. <https://grantable.co/>,
  <https://www.grantable.co/features/ai-grant-writing-assistant>. Verdict: the
  content-library-reused-across-proposals idea is a *narrative* cousin of C4's
  substrate; no budget model, no fractions, no checks.
- **Granted AI** — Granted AI (usegrantedai.com). Funder matching (990-derived
  profiles), RFP analysis, section-by-section drafting, simulated 6-reviewer
  "committee review." Budget appears only as interview questions that ground
  the narrative. Free tier / ~$89 per month.
  <https://grantedai.com/features>. Verdict: no C1–C6 contact; its "committee
  review" is stochastic LLM critique, not machine-checkable validation (C5
  contrast).
- **Grant Assistant** — FreeWill (acquired 2024). AI drafting trained on
  winning proposals; RFP → requirements matrix; "scans every proposal against
  a generated matrix of requirements to catch gaps before submitting."
  Commercial SaaS.
  <https://www.nonprofits.freewill.com/products/grant-assistant>. Verdict:
  nearest Lane-1 neighbor to C5 — but the requirements matrix is LLM-generated
  per proposal, not a versioned, citable rule pack, and the check is advisory
  prose, not a deterministic exit code / status artifact.
- **Streamline** — Streamline Climate, Inc. AI grant/RFP pipeline for climate
  tech and infrastructure applicants: opportunity search, solicitation
  summarization ("chat with your solicitation"), drafting, reuse of past
  responses. Commercial SaaS.
  <https://streamlineclimate.com/solutions/startup>. Verdict: narrative only;
  no budget compilation, no cross-application accounting.
- **Grantboost** — Grantboost.io. Survey-driven LLM proposal generation;
  honors word/character limits per section. Free tier / from ~$32 per month.
  <https://www.grantboost.io/nonprofits/>. Verdict: enforcing a word limit at
  generation time is the germ of a funder rule, but there is no encoded pack,
  no lint, no artifact (C5 contrast).
- **Submittable (applicant side)** — Submittable Holdings. Applicants fill
  funder-built web forms; eligibility screeners gate entry; required-field and
  type validation. <https://submittable.help/en/articles/3872413-eligibility-forms>.
  Verdict: touches C5 — machine-gated eligibility exists, but rules live
  inside the funder's portal, invisible and unversioned from the applicant's
  side; validation is of form fields, not of a budget model.
- **OpenGrants** — OpenGrants (opengrants.io). Grant search engine (70k+
  listings), freelance grant-writer marketplace, REST API over listings.
  Despite the name, not open-source tooling; it is open *data access* to
  opportunity listings. <https://opengrants.io/for-grant-seekers/>. Verdict:
  no claim contact.
- **LogicBalls "AI Grant Budget Template"** (representative of a genre) —
  free prompt tool that has an LLM write a budget table from a project
  description. <https://logicballs.com/tools/grant-budget-template>. Verdict:
  C1 contrast in its purest form — the budget is generated text with no
  underlying model; re-running it does not reproduce it.

**Lane 1 net:** kills nothing. Strongest neighbor: FreeWill's requirements
matrix (C5-adjacent, non-deterministic).

## 2. Grants management systems (funder side)

Lane question: does any GMS expose applicant-side budget composition or
machine-checkable application validation? **Finding: all validate form fields
and workflow state; none sees inside the applicant's cost model, and none
checks allocation across a portfolio of applications to *other* funders.**

- **Fluxx Grantmaker** — Fluxx.io. Funder GMS: configurable forms and
  workflows, grantee portal, budget/finance tracking of awards, automated
  validation steps in workflows (required fields, data standardization).
  Enterprise SaaS.
  <https://www.fluxx.io/products/grantmaker-fluxx-grants-management-software>.
  Verdict: C5 contrast — validation exists but is portal-side, closed, and
  per-form; budgets are attachments/line tables, not compiled artifacts (C1).
- **Foundant GLM** — Foundant Technologies. Application → review → payment →
  follow-up for small/mid foundations; form builder with branching; budgets
  tracked as program-level allocations drawn down by payments. SaaS.
  <https://www.foundant.com/products/grant-management-software-for-foundations/>.
  Verdict: no claim contact beyond form validation (C5 contrast).
- **Submittable (funder side)** — form building, eligibility gates, staged
  review, "validating data provided across third-party databases for
  eligibility" (per help center). <https://www.submittable.com/features/online-forms>.
  Verdict: same as Lane 1 entry — C5's machinery exists in closed portals.
- **SmartSimple Cloud** — SmartSimple Software. Highly configurable GMS
  (foundations, government, research funders): Application Manager with
  eligibility quizzes and IRS/watchlist vetting; Budget Manager for funder-side
  budget/payment schedules driven by business rules.
  <https://www.smartsimple.com/solution/grants-management-tracking-software>.
  Verdict: "business rules" govern *funder* payments, not applicant budget
  composition; C2/C4 untouched.
- **Salesforce grantmaking** — Outbound Funds Module (free, open-source
  Salesforce package: funding programs, requests, disbursements, GAU
  expenditures) and Nonprofit Cloud for Grantmaking (commercial, portal +
  richer data model).
  <https://appexchange.salesforce.com/appxListingDetail?listingId=a0N3A00000G5vDxUAJ>.
  Verdict: notable as the lane's one open-source artifact, but it models
  money movement, not application content or budget derivation.
- **Blackbaud Grantmaking** — Blackbaud. Funder budget hierarchies
  (categories → reserve funds → line items), payment appropriation controls,
  applicant portal + AI form builder (2024).
  <https://webfiles-sc1.blackbaud.com/files/support/helpfiles/grantmaking/content/budget-phase1.html>.
  Verdict: budget machinery is entirely funder-internal; no view into
  applicant cost structure.
- **WizeHive Zengine** — WizeHive (now part of Submittable ecosystem
  competitors). Flexible form/review/workflow builder for grants,
  scholarships, awards. <https://softwareconnect.com/reviews/wizehive-zengine/>.
  Verdict: no claim contact.
- **AmpliFund (Euna Grants)** — grant lifecycle for governments receiving and
  passing through funds; budgets, indirect costs, staff hours tracked through
  the award lifecycle. <https://www.amplifund.com/features/>. Verdict: closest
  GMS to budget mechanics (indirect-cost tracking), still award-tracking, not
  proposal compilation.

**Lane 2 net:** kills nothing. Machine validation of applications is
ubiquitous *inside closed funder portals* — which sharpens rather than kills
C5: the novelty left is applicant-side, versioned, open, funder-portable rule
packs with a repo-resident status artifact.

## 3. Nonprofit budgeting / finance tools

Lane question: does anything do multi-funder allocation with
double-billing/effort checks **pre-award**? **Finding: multi-funder
allocation is a solved *post-award accounting* problem and a supported
*budget-planning* feature; nothing gates allocation across simultaneous
not-yet-awarded proposals.**

- **Sage Intacct (nonprofit)** — Sage. Fund accounting with grant tracking &
  billing: allocate expenses to grants across AP/PO/GL/expenses/timesheets,
  bill indirect at negotiated/specific/markup rates, track employee effort per
  grant from timesheets, budget-vs-actual to flag unallowable spend.
  Enterprise SaaS.
  <https://www.sage.com/en-us/sage-business-cloud/intacct/product-capabilities/extended-capabilities/grants-tracking-billing/>.
  Verdict: touches C2 from the post-award side — fund segregation and
  allocation rules are how double-charging is prevented *after* award, by
  bookkeeping discipline, not by a pre-award machine gate. Also C3 contrast:
  indirect/fringe as configured rates, not law.
- **Martus** — Martus Solutions. Nonprofit budgeting/forecasting; personnel
  budgeting explicitly supports employees "funded by multiple grants,"
  allocated by hours, amount, or percentage, by month or year. SaaS.
  <https://www.martussolutions.com/capabilities/personnel>. Verdict: nearest
  Lane-3 neighbor to C2/C4 — a person split across grants with percentages is
  the same object as a co-funding fraction. But it is an internal planning
  worksheet for known/expected funding: no notion of *simultaneous pending
  applications*, no constraint that fractions across open proposals sum ≤ 1,
  no machine gate, no artifact a funder sees.
- **Limelight FP&A** — Limelight Software. Nonprofit FP&A with templates for
  grants, funds, programs, workforce planning; integrates with
  QuickBooks/Intacct/etc. SaaS. <https://www.golimelight.com/industries/non-profit>.
  Verdict: same shape as Martus; planning, not gating.
- **Propel Nonprofits — True Program Costs template** — free spreadsheet +
  guide for program-based budgeting and admin-cost allocation.
  <https://propelnonprofits.org/resources/true-program-costs-program-budget-and-allocation-template-and-resource/>.
  Verdict: C1 contrast — the sector's state of the art for "budget from
  structure" is a spreadsheet with formulas: computed, but not versioned,
  testable, or reproducible outside the workbook.
- **Wallace Foundation StrongNonprofits toolkit** — free templates including
  a *Program-Based Budget Builder* (allocates personnel and shared costs to
  programs) and an out-of-school-time cost calculator ("works like a mortgage
  calculator").
  <https://wallacefoundation.org/toolkit/strongnonprofits-toolkit?s=budgeting>,
  <https://wallacefoundation.org/sites/default/files/2023-10/program-based-budget-builder-overview.pdf>.
  Verdict: the cost calculator is a genuine (closed-form) cost model exposed
  to planners — a C6 ancestor, but generic benchmarks, not the org's own live
  model, and not funder-facing diligence.
- **Indirect-cost practice** — 2 CFR 200 de minimis rate (10%, raised to 15%
  in the 2024 OMB revision) or a negotiated NICRA; implemented in budgets as a
  multiplier row. Verdict: C3 contrast — the entire compliance apparatus
  standardizes *multipliers*, which is exactly what C3 replaces with computed
  statutory costs.
- **Fund-accounting validation genre** (Aplos, MIP, FastFund, etc.) —
  validation rules that prevent charging the wrong fund; allocation rules that
  distribute an expense across funds on entry.
  <https://www.criadv.com/insight/managing-restricted-funds/>. Verdict: C2's
  "don't bill twice" invariant exists in production software — *post-award,
  expense-by-expense*. The pre-award, proposal-fraction version is not found.

**Lane 3 net:** kills nothing; establishes that the ≤100% allocation object
exists in planning tools (Martus) and the double-charging invariant exists in
accounting tools (Intacct et al.), both outside the pre-award window.

## 4. Federal compliance machinery

Lane question: what exists for cross-application allocation checking, and is
any of it pre-award/automatic vs post-award/manual attestation? **Finding:
the *rule* (no >100% commitment; no double-charging) is old and explicit; the
*enforcement* is human at every pre-award point found. Budget arithmetic and
form validation, by contrast, are heavily automated (ASSIST, Grants.gov,
Cayuse, Kuali) — inside closed systems.**

- **Effort certification: Huron ECC (née ecrt)** — Huron Consulting Group.
  The dominant university system for 2 CFR 200.430 personnel-cost compliance:
  generates effort/payroll statements per period which PIs *certify after the
  fact* (traditional effort reporting or project-based payroll confirmation).
  Commercial, closed.
  <https://www.huronconsultinggroup.com/-/media/Resource-Media-Content/Education/research-suite/Huron-Research-Suite-Employee-Compensation-Compliance.pdf>,
  <https://finance.uw.edu/pafc/effort-reporting/ecc-system/ecc-overview>.
  Verdict: strong C2 evidence *for* novelty — the incumbent solution to
  cross-source personnel allocation is post-award attestation, workflow-managed
  but substantively human.
- **Maximus Effort Reporting System** — Maximus. Same category: web-based
  after-the-fact effort certification with escalation workflows.
  <https://maximus.com/specialized-markets/higher-ed/effort-reporting-system-and-services>.
  Verdict: as above.
- **Current & pending / Other Support (NIH, NSF)** — the policy layer for C2.
  NIH: commitment overlap (>100% / >12 person-months across all support) "is
  not permitted" and "will be resolved by the IC with the applicant and the
  PD/PI at the time of award" — i.e., detected by staff reading JIT
  submissions, resolved by negotiation (NIH GPS §2.5.1;
  <https://grants.nih.gov/grants/policy/nihgps/HTML5/section_2/2.5.1_just-in-time_procedures.htm>;
  UW–Madison summary <https://rsp.wisc.edu/other-support-information.cfm>).
  University pre-award offices review C&P forms so listed effort sums to
  ≤100%/12 months (e.g., Tufts OVPR guidance,
  <https://viceprovost.tufts.edu/policies-forms-guides/current-and-pending-other-support-proposals-and-awards>).
  NSF's C&P FAQ describes use of the data to assess overcommitment but no
  automated check
  (<https://www.nsf.gov/funding/senior-personnel-documents/faq/current-pending>).
  No evidence found of any agency system that automatically sums commitments
  across applications; guidance uniformly describes staff review. Verdict:
  the closest *practice* to C2 anywhere — the constraint is standard; the
  machine gate is absent. C2 survives on the "machine-checked, pre-award"
  qualifier, and the paper should cite this lineage explicitly.
- **NIH ASSIST / eRA validations** — era.nih.gov. Applications are validated
  against "many NIH business rules" pre-submission; errors block submission,
  warnings don't; failures produce an itemized Errors and Warnings results
  page. Free to applicants, closed system.
  <https://www.era.nih.gov/about-era/other-services/validations>,
  <https://www.era.nih.gov/erahelp/assist/Content/ASSIST_Help_Topics/5_Preview_Print_Submit/Submit_Validated_Application.htm>.
  Verdict: **strongest single prior art against C5.** Machine-encoded funder
  rules + automatic validation + a structured error/warning report existed
  here first. What it is not: open, versioned, applicant-side, or portable —
  the rules are opaque implementation, the "artifact" is a transient results
  page, and only federal NIH-family forms are covered.
- **Grants.gov Workspace + forms repository** — HHS/OMB. "Check for Errors"
  and Check Application run field- and cross-form validation (e.g., budget
  totals must reconcile between SF-424A detail and summary) before
  submission, documented in Grants.gov help; the grantor and applicant
  system-to-system pages publish versioned XML schemas for
  opportunity/application handling (e.g., GrantsCommonTypes-V1.0,
  GrantsCommonElements-V1.0, ApplicantCommonElements-V1.0,
  GrantsFundingSynopsis-V2.0, marked Schema Version V2.0-compatible).
  Individual SF-424-family form XSDs were NOT confirmed on the public pages
  (2026-08-14 live check: the forms-repository page serves sample PDFs that
  "cannot be submitted").
  <https://www.grants.gov/applicants/encountering-error-messages.html>,
  <https://grants.gov/forms/forms-repository/sf-424-family>,
  <https://www.grants.gov/system-to-system/grantor-system-to-system/schemas>.
  Verdict: partial prior art for C5's "form rules as code, versioned":
  federal system-to-system *interchange* is literally versioned schema
  (per-form XSD publication unverified); business rules and caps are only
  partly encoded, the validator is a hosted black box, and nothing lands in
  the applicant's repo.
- **Cayuse 424 / Cayuse SP** — Cayuse (research administration). System-to-
  system proposal builder that maintains a running errors/warnings/info list
  replicating Grants.gov and agency validations; budgets auto-calculated from
  institutional profiles (fringe rate tables, 3% inflation escalation, 1%/yr
  fringe drift, F&A averaging across fiscal years). Commercial, university
  market. <https://support.cayuse.com/hc/en-us/articles/115013731528>,
  <https://support.cayuse.com/hc/en-us/articles/115013737108-Adding-Fringe-Rates-and-Benefits-in-Proposals-S2S>.
  Verdict: prior art against both C5 (live validation with severity levels)
  and C1's weak form (budget computed from structured inputs + rate tables).
  What's missing for C1 proper: the inputs are cost categories and rates, not
  a work-item menu; the computation is interactive and stateful, not a pure
  function; nothing is reproducible outside the vendor system.
- **Kuali Research budget engine** — Kuali (commercial SaaS). Lineage: MIT
  Coeus → Kuali Coeus (2006, community source under the Educational Community
  License, Kuali Foundation) → 2014 for-profit spin-off (KualiCo, later
  Kuali) → Kuali Research. The open-source ancestor
  (<https://github.com/kuali/kc>, AGPL-3.0) is real open source and not
  archived, but frozen: last commit 2017-01-06, last push 2018-05-16
  (verified 2026-08-14); the current commercial engine is closed.
  Institutional rate tables (F&A, fringe, inflation, vacation) drive automatic
  budget calculation "on a precise daily calculation," including cost share
  and unrecovered F&A.
  <https://kuali-research.zendesk.com/hc/en-us/articles/115010656047-Proposal-Budget-Budget-Engine-Calculations>.
  Verdict: same as Cayuse for C1; also the sharpest C3 contrast in the wild —
  fringe is *defined* as salary × configured rate; no one computes it from
  statute. Precision note: not simply "closed" — an open ancestor exists,
  frozen since 2017.
- **APD / FFP practice (state HHS systems)** — 45 CFR 95.610 requires states
  to submit Advance Planning Documents with a proposed budget and "an estimate
  of the prospective cost allocation/distribution to the various State and
  Federal funding sources" *before* acquiring systems; CMS/ACF fund at
  enhanced FFP rates (90/75/50) and offer a Cost Allocation Methodology (CAM)
  toolkit for splitting costs across programs; multi-program APDs cover
  systems funded by several federal programs at once.
  <https://www.law.cornell.edu/cfr/text/45/95.610>,
  <https://www.medicaid.gov/federal-policy-guidance/downloads/faq061319.pdf>,
  <https://acf.gov/sites/default/files/documents/ocse/apd_guide_2.pdf>.
  Verdict: the closest *pre-award* multi-funder allocation practice found
  anywhere — conceptually C2+C4 (one system, several federal funders, declared
  shares, approval before spend). Implementation: narrative documents,
  spreadsheet methodologies, human federal reviewers. No machine check, no
  code, no reproducibility. The paper should cite this as the manual ancestor.
- **SF-424A itself** — the government-wide budget form: Section A/B matrices
  by object class and funding source, totals that must reconcile. Tooling =
  fillable PDF plus the validators above.
  <https://grants.gov/forms/forms-repository/sf-424-family>. Verdict: C1
  contrast — the canonical grant budget is a *form*, downstream of whatever
  spreadsheet produced the numbers; provenance ends at data entry.

**Lane 4 net:** wounds C5 (validation with status reporting exists at scale,
closed) and weak-C1 (rate-table budget engines exist, closed); strengthens C2
(the rule is everywhere, the machine gate nowhere) and frames C4's APD
ancestor.

## 5. Docs-as-code / CI applied to documents

Lane question: prior art for the *pattern* — and anything literally styled
"grants as code" or "CI for grants"? **Finding: the pattern is mature in
adjacent domains (security compliance, legal, prose style, scientific
publishing). The exact phrases return nothing tool-shaped for grant
applications; the nearest live practice is crypto grant programs run as
markdown PRs.**

- **Exact-phrase search** — "grants as code": no tool, paper, or product
  found using the phrase for grant applications (results are license/crypto
  noise). "CI for grants": nothing on point. Verdict: the framing appears
  unclaimed as of 2026-08.
- **Git-native grant programs** — Web3 Foundation Grants-Program, gno.land
  grants, Secret Labs: applications are markdown files submitted by pull
  request and reviewed in-repo. <https://github.com/w3f/Grants-Program>,
  <https://github.com/gnolang/grants>. Verdict: real prior art for
  *proposals in git with PR review* — but the artifact is narrative-only; no
  budget model, no funder rule packs, no machine validation of content
  claimed. Cite and distinguish.
- **OSCAL + compliance-trestle** — NIST schema + IBM-originated
  oscal-compass project: security compliance documents (SSPs, catalogs)
  authored as markdown/JSON in git, validated and assembled by CLI "designed
  to operate as a CI/CD pipeline running on top of compliance artifacts in
  git." Open source (Apache-2.0).
  <https://github.com/oscal-compass/compliance-trestle>,
  <https://oscal.io/tools/>. Verdict: **the strongest pattern-level prior art
  for C5** — versioned rule schemas + CI validation + generated documents, in
  a different compliance domain. C5's residual novelty is domain transfer
  (funder packs, budget caps, submission formats), not the pattern.
- **Vale** — open-source prose linter; styles are YAML rule packages run in
  CI on docs PRs (used by Grafana, Datadog, Elastic docs teams).
  <https://vale.sh/>. Verdict: prior art for "lint text against a rule pack
  in CI" generally; grantkit's `check` is Vale-shaped with funder semantics
  (limits, required sections, citations, budget caps).
- **docassemble** — Jonathan Pyle, MIT license. Guided interviews (YAML +
  Python + Markdown) assemble legal documents (PDF/DOCX) from structured
  data; the Suffolk LIT Lab Assembly Line builds court forms on it.
  <https://docassemble.org/>. Verdict: documents-compiled-from-data is
  established in legal aid; no budgets, no funder rules.
- **Catala / Accord Project** — law and contracts as executable code: Catala
  (Inria) transcribes statutes into a verified DSL, used with French tax/
  benefits administrations; Accord Project makes contracts with computable
  components. <https://www.inria.fr/en/catala-software-dgfip-cnaf>,
  <https://docs.accordproject.org/docs/accordproject-slc.html>. Verdict:
  legitimizes C3's premise (statute → code is a proven technique); nobody has
  pointed it at grant budgets.
- **Quarto / LaTeX in CI** — scientific manuscripts routinely render and
  check in CI (e.g., quarto-dev/quarto-actions on GitHub; Overleaf's git
  bridge). Verdict: background practice the paper builds on; no grant
  semantics.
- **OPA / policy-as-code** — general-purpose policy engines (Rego) evaluate
  structured inputs in CI; applied to infrastructure, Kubernetes, and (via
  OSCAL tooling) compliance data. No application to grant forms/budgets
  found. Verdict: pattern prior art only.

**Lane 5 net:** kills any claim that the *pattern* (documents + rules + CI +
status artifacts) is new — trestle/Vale/docassemble own it. All six claims
must therefore rest on the grant-domain objects (menus, fractions, funder
packs, statutory rates), which is where the sweep found no occupants.

## 6. Compensation benchmarking for budgets

Lane question: does any tool compute LOADED costs (payroll tax + retirement
caps) from rules rather than multipliers? **Finding: benchmarks are data
products; loading is either a flat multiplier (grant practice) or a
rules-based calculation in *payroll/hiring* tools that never touches grant
budgets and carries no benchmark provenance.**

- **Candid Nonprofit Compensation Report** — Candid (GuideStar). Annual
  study of executive comp from IRS 990s (2025 edition: 217k records, 131k
  orgs); positions × budget band × geography. Paid report.
  <https://candid.org/nonprofit-compensation-report/>. Verdict: benchmark
  *source* for C3's provenance leg; static PDF/data product, no cost
  computation.
- **ERI Nonprofit Comparables Assessor** — ERI Economic Research Institute.
  990-derived comp comparables for 55 executive positions; supports
  "rebuttable presumption of reasonableness" documentation; budget module
  tracks comp against department budgets. Subscription.
  <https://www.erieri.com/nonprofitcomparablesassessor>. Verdict: same —
  benchmarks + audit rationale, no statutory loading.
- **BLS OEWS** — Bureau of Labor Statistics. Public wage percentiles for
  ~830 occupations, national/state/metro; the standard citation for salary
  reasonableness in budget justifications. <https://www.bls.gov/oes/>.
  Verdict: the provenance substrate C3 consumes; BLS publishes data, not
  loaded-cost tooling.
- **"True cost of employee" calculators** — genre of free web calculators
  (e.g., <https://jupid.com/payroll-tax-calculator>,
  <https://truetools.org/tools/employee-cost-calculator-usa>) computing
  employer FICA/FUTA/SUTA (some citing IRS Pub 15 parameters) plus rule-of-
  thumb benefits/overhead percentages. Verdict: partial prior art for C3's
  *computation* — employer tax from encoded rules exists as throwaway web
  tools; none handles retirement-plan employer caps as law, none carries
  benchmark provenance, none feeds a budget artifact.
- **Payroll engines (ADP, Gusto, et al.)** — production payroll computes
  actual employer burden from encoded tax law every pay run. Verdict: proves
  C3's computation is feasible and standard *post-hire*; no pre-award
  budgeting product surfaces it. (No vendor doc found marketing payroll-grade
  loading for grant budgets.)
- **Grant-practice loading** — universities and nonprofits budget personnel
  as salary × pooled fringe rate (Kuali/Cayuse mechanics above; NICRA
  culture). Verdict: the incumbent C3 answer is a multiplier everywhere.

**Lane 6 net:** C3's parts all exist separately (benchmarks: Candid/ERI/BLS;
rules-based loading: payroll engines and web calculators; multiplier culture:
everywhere). Composing them into a reproducible pre-award rate artifact with
provenance is the unoccupied square.

## 7. Adjacent fields the paper must address

Not in the assigned lanes, but the closest conceptual neighbors found; a
referee will raise them.

- **GovCon proposal pricing: Deltek ProPricer** — structured cost buildup
  (labor categories, indirect rate structures, escalation, CLINs) generating
  FAR-15/DCAA-defensible cost volumes; since 1984. Commercial.
  <https://www.propricer.com/>. Verdict: **the strongest C1 neighbor in any
  industry** — budgets computed from structured cost elements and rate math,
  reused across proposals. Differences that keep C1 alive: closed, priced in
  labor-category hours not work items with completion evidence, no
  cross-proposal allocation constraint, no CI/reproducibility story, wrap
  rates are pooled multipliers (C3 contrast).
- **BOEMax (ProjStream)** — basis-of-estimate software: a central library of
  process templates (tasks + labor + materials) and historical actuals,
  reused across proposals for consistent estimates. Commercial.
  <https://www.projstream.com/basis-of-estimate-proposal-software-boemax>.
  Verdict: nearest neighbor to C4's *menu* — a reusable priced work library
  feeding many proposals. No co-funding fractions (GovCon prices one contract
  at a time), no sum≤1 gate, no funder-facing view.
- **Construction estimating (RSMeans data, Gordian)** — priced work-item
  catalogs (assemblies/unit costs) compiled into bids by estimating software;
  decades old. Verdict: C1's "priced menu → budget" is ancient in
  construction; the grant-domain novelty is the menu carrying *machine-
  checkable completion evidence* and compiling under funder rule packs.
- **Philanthropy Data Commons** — open-source (GitHub:
  PhilanthropyDataCommons/service) shared-data infrastructure so nonprofits
  enter org/proposal data once and multiple funders read it via API; backed
  by major foundations. <https://philanthropydatacommons.org/>. Verdict:
  C4-adjacent on the *data* axis — one substrate, many funders — but the
  shared objects are org profiles and proposal metadata, not priced work
  items, and there is no budget or allocation semantics.
- **Common grant applications (regional grantmaker associations, JustFund)**
  — shared application forms accepted by multiple funders.
  <https://learning.candid.org/resources/knowledge-base/common-grant-application/>.
  Verdict: C4's inverse — N funders, one *form*; no org-side substrate, no
  fractions.
- **Braided/blended funding practice** — HHS/ASPE toolkit, Mathematica's
  ECE braiding tool, TFAH compendium: established methodology for financing
  one program from several funding streams with cost-allocation discipline
  ("each funder pays its share, no double-charging").
  <https://ecbraiding.mathematica.org/>,
  <https://www.aspe.hhs.gov/sites/default/files/2021-08/EC_Braiding_Toolkit.pdf>.
  Verdict: C2/C4's conceptual ancestor in program finance — guides and
  spreadsheets, human-enforced; no machine gate.
- **DonorsChoose** — itemized classroom projects: every project shows a
  vendor-priced manifest; donors fund real line items; price deltas
  reconciled by policy. <https://help.donorschoose.org/hc/en-us/articles/201936606-Vendor-pricing>.
  Verdict: nearest C6 neighbor — funders browsing real, priced, itemized
  need — but items are retail SKUs, not the org's cost model, and there is
  no configurator over rates/assumptions.
- **Open Collective** — open-source platform where a collective's full
  ledger (income, expenses, balance) is public by default; funders watch the
  live budget. <https://docs.opencollective.com/help/product/ledger>.
  Verdict: C6-adjacent transparency — live *actuals*, not a forward cost
  model; no selection/toggle semantics.
- **Manifund** — open-source regranting site: public projects with funding
  goals, public grant ledger, impact-certificate experiments.
  <https://manifund.org/>. Verdict: funder-facing project marketplace;
  budgets are prose numbers, not models.

---

## Claim adjudication

**C1 — Budgets as compiled artifacts.** AGAINST: rate-driven budget engines
(Kuali, Cayuse) compute budgets from structured inputs; ProPricer/BOEMax
compile cost volumes from cost element libraries; construction estimating
compiles bids from priced catalogs; every serious nonprofit budget is already
formula-driven in a spreadsheet. FOR: all of the above are closed or, where
once open, frozen since 2017 (Kuali's AGPL ancestor), and all are
interactive and category-based; none is a pure function over a versioned
work-item menu, none reruns in CI, none ties items to completion evidence.
**Verdict: PARTIAL PRIOR ART** — claim survives only in its precise form
("pure function, work-item menu, reproducible in CI"); the loose form
("computing budgets from data") is dead and the paper should concede it.

**C2 — Pre-award cross-application double-billing gate.** AGAINST: the
constraint itself is canonical federal policy (NIH commitment overlap,
NSF C&P), university pre-award offices review for it, Martus plans multi-grant
splits, fund accounting enforces single-charging post-award, and APDs declare
multi-funder shares before spend. FOR: every pre-award instance found is
human review of self-reported forms — NIH resolves overlap "at the time of
award" by conversation; no system found that mechanically sums per-item (or
per-person) fractions across simultaneous open applications and fails a
build. **Verdict: NOVEL (as a machine check)** — with the explicit caveat
that the *invariant* is old; novelty is enforcement timing + automation.

**C3 — Rule-derived personnel rates.** AGAINST: payroll engines compute
employer burden from encoded law daily; free calculators do FICA/FUTA/SUTA
from published parameters; Candid/ERI/BLS provide benchmark provenance as
products; grant practice has a complete, compliant answer (pooled fringe
rates, NICRA, de minimis). FOR: no tool found that composes statutory
loading + benchmark provenance into a citable pre-award rate object inside a
budget compilation; in grant tooling, fringe is definitionally a multiplier.
**Verdict: PARTIAL PRIOR ART** — the computation and the benchmarks both
exist; the composition and placement (pre-award, provenance-carrying,
compiled) do not.

**C4 — Funder-as-view.** AGAINST: BOEMax reuses one estimate library across
proposals; PDC shares one org dataset with many funders; common grant apps
share one form; braided-funding practice allocates one program across
funders; Grantable-style content libraries reuse narrative. FOR: no system
found where N live proposals are *selections with fractions* over one priced
substrate such that views stay consistent by construction; in every neighbor
the reuse is copy-forward (estimates, text, data), not a constrained view.
**Verdict: NOVEL (as a mechanism)** — with named conceptual ancestors (BOE
libraries, PDC, braiding) the paper should cite.

**C5 — Versioned funder packs + CI validation + status artifact.** AGAINST:
NIH ASSIST/eRA validate against encoded business rules with itemized
errors/warnings; Grants.gov publishes versioned system-to-system XML schemas
and documents cross-form checks (per-form XSD publication unverified);
Cayuse replicates agency validations with severity levels;
Submittable/Fluxx gate eligibility in-portal; OSCAL/trestle already do
versioned rule packs + CI + generated compliance documents in another domain;
Vale already does rule-pack linting of prose in CI. FOR: no applicant-side,
open, funder-portable rule packs with citations/provenance; no philanthropic
funder coverage; no repo-resident machine-readable status artifact. **Verdict:
EXISTS (core) / PARTIAL PRIOR ART (packaging)** — the paper must claim only
the *open, versioned, applicant-side, any-funder* packaging, and cite ASSIST
+ trestle as the two halves it joins.

**C6 — Funder-facing configurator over the org's live cost model.** AGAINST:
DonorsChoose lets funders shop itemized real-cost projects; Open Collective
exposes live ledgers; Manifund exposes public projects and gaps; Wallace ships
a generic program-cost calculator. FOR: none of these hands a funder
presets/toggles over the *organization's own* menu and rate model with
budgets recomputed live; the neighbors expose items, actuals, or generic
models, not the org's compiled forward model. **Verdict: NOVEL** — thinnest
evidence base of the six (fewest neighbors to test against), and the paper
already flags adoption as untested beyond one live diligence.

## Summary table

| Claim | Verdict | Nearest neighbor | Citation |
|---|---|---|---|
| C1 budget as compiled artifact | PARTIAL PRIOR ART | Kuali Research budget engine (rate-table autocalc; open-source ancestor frozen since 2017); Deltek ProPricer (structured cost buildup) | <https://kuali-research.zendesk.com/hc/en-us/articles/115010656047-Proposal-Budget-Budget-Engine-Calculations>; <https://www.propricer.com/> |
| C2 pre-award double-billing gate | NOVEL (machine check; invariant is old policy) | NIH commitment-overlap rule, staff-resolved at award; Huron ECC post-award certification | <https://grants.nih.gov/grants/policy/nihgps/HTML5/section_2/2.5.1_just-in-time_procedures.htm>; <https://finance.uw.edu/pafc/effort-reporting/ecc-system/ecc-overview> |
| C3 rule-derived personnel rates | PARTIAL PRIOR ART | Payroll-tax calculators/engines (rules-based loading, no provenance, post-hire); pooled fringe multipliers (incumbent) | <https://jupid.com/payroll-tax-calculator>; <https://support.cayuse.com/hc/en-us/articles/115013737108-Adding-Fringe-Rates-and-Benefits-in-Proposals-S2S> |
| C4 funder-as-view | NOVEL (mechanism; ancestors are copy-forward reuse) | BOEMax process/estimate library reused across proposals; Philanthropy Data Commons (one dataset, many funders) | <https://www.projstream.com/basis-of-estimate-proposal-software-boemax>; <https://philanthropydatacommons.org/> |
| C5 versioned funder packs + CI + status artifact | EXISTS (core) / PARTIAL (open, applicant-side packaging) | NIH ASSIST business-rule validation with error/warning report; OSCAL compliance-trestle (rule packs in git + CI) | <https://www.era.nih.gov/about-era/other-services/validations>; <https://github.com/oscal-compass/compliance-trestle> |
| C6 funder-facing configurator | NOVEL (weakest neighbor set, adoption untested) | DonorsChoose itemized vendor-priced projects; Open Collective live public ledger | <https://help.donorschoose.org/hc/en-us/articles/201936606-Vendor-pricing>; <https://docs.opencollective.com/help/product/ledger> |

Exact-phrase check: no prior tool or paper styled "grants as code" or "CI for
grants" was found (2026-08 sweep); nearest live practice is crypto grant
programs run as markdown PRs (<https://github.com/w3f/Grants-Program>).

Citation/verification note (2026-08-14 live checks): Kuali lineage and repo
status confirmed against <https://github.com/kuali/kc> (AGPL-3.0; not
archived; last commit 2017-01-06, last push 2018-05-16) — hence the C1
"closed or, where once open, frozen since 2017" wording. Grants.gov schema
claims narrowed to what the system-to-system pages actually publish
(GrantsCommonTypes/GrantsCommonElements/ApplicantCommonElements/
GrantsFundingSynopsis, marked Schema Version V2.0-compatible); per-form
SF-424 XSDs were not found on the public pages, and cross-form budget
reconciliation rests on Grants.gov help ("Check for Errors").
