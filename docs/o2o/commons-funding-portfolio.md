# Commons Funding Portfolio

The Commons funding portfolio aggregates persisted PNEUMA/MENDER
funding evidence for human observation.

It is a read-only portfolio view.

## Important identity rule

A persisted evidence bundle is an observation record.

It is not automatically treated as a unique grant.

Therefore:

    PORTFOLIO_RECORD != UNIQUE_GRANT

Repeated observations may describe the same proposal.

Stable proposal identity is intentionally deferred to a separate
identity milestone rather than inferred from incomplete metadata.

## Inputs

    PNEUMA/evidence/funding/mender/ledger.jsonl
    PNEUMA/evidence/funding/mender/bundles/*

## Outputs

    funding-portfolio.json
    index.html

## Portfolio summaries

The surface may summarize:

- MENDER classifications
- observed completion percentages
- GrantKit validation errors
- GrantKit validation warnings
- deadline states
- coordination queue counts
- evidence bundle identities

## Governance boundary

The portfolio may not:

- approve a proposal
- authorize submission
- submit a proposal
- execute a queue item
- mutate GrantKit
- mutate PNEUMA evidence
- change authority state

Truth distinctions:

    PORTFOLIO_RECORD != UNIQUE_GRANT
    PORTFOLIO_VISIBILITY != APPROVAL
    PORTFOLIO_PRIORITY != AUTHORIZATION
    OBSERVED != AUTHORIZED
    QUEUED != EXECUTED
    EVIDENCE != PERMIT
    MENDER != GOVERNOR

Defaults:

    PORTFOLIO_CAN_AUTHORIZE=FALSE
    PORTFOLIO_CAN_SUBMIT=FALSE
    PORTFOLIO_CAN_EXECUTE=FALSE
    PORTFOLIO_CAN_MUTATE_SOURCE=FALSE
    AUTHORITY_CHANGED=FALSE
