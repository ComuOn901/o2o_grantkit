# Paraclete / Commons Funding Observation Surface

The funding observation surface consumes persisted MENDER/PNEUMA
evidence and renders it for human review.

It is observational only.

## Inputs

    PNEUMA/evidence/funding/mender/ledger.jsonl
    PNEUMA/evidence/funding/mender/bundles/*

## Outputs

    funding-observation.json
    index.html

## Capabilities

The surface may:

- display proposal metadata
- display GrantKit validation state
- display MENDER classification
- display MENDER coordination queues
- display PNEUMA evidence bundle identity
- display governance truth state

The surface may not:

- authorize submission
- submit proposals
- execute queued tasks
- mutate evidence
- mutate GrantKit source
- change governance state

## Truth boundary

    OBSERVED != AUTHORIZED
    QUEUED != EXECUTED
    EVIDENCE != PERMIT
    MENDER_COORDINATION != AUTHORIZATION

Defaults:

    SURFACE_CAN_AUTHORIZE=FALSE
    SURFACE_CAN_SUBMIT=FALSE
    SURFACE_CAN_EXECUTE=FALSE
    SURFACE_CAN_MUTATE_SOURCE=FALSE
    AUTHORITY_CHANGED=FALSE
