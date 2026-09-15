# MENDER Funding Evidence Persistence

MENDER funding coordination state may be persisted into PNEUMA as
evidence.

The persistence layer records coordination state. It does not grant
authority.

## Flow

    GrantKit
        |
        v
    status.json
        |
        v
    o2o-funding-state.json
        |
        v
    MENDER read interface
        |
        v
    MENDER machine-readable view
        |
        v
    PNEUMA evidence bundle

Each bundle contains:

    manifest.json
    mender-view.json
    queue.json

PNEUMA also maintains:

    ledger.jsonl

The ledger is append-only evidence indexing.

## Truth boundary

    EVIDENCE_PERSISTED != AUTHORIZATION
    QUEUE_PERSISTED != AUTHORIZATION
    QUEUE_PERSISTED != EXECUTION
    MENDER_COORDINATION != AUTHORIZATION

MENDER may persist:

- proposal observations
- classifications
- coordination queues
- artifact hashes
- evidence metadata

MENDER may not:

- authorize submission
- submit a proposal
- create a governor decision
- claim execution from queue creation
- change authority state

Defaults:

    MENDER_CAN_AUTHORIZE=FALSE
    MENDER_CAN_SUBMIT=FALSE
    AUTHORIZATION_OCCURRED=FALSE
    EXECUTION_OCCURRED=FALSE
    AUTHORITY_CHANGED=FALSE
