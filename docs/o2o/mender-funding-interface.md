# MENDER Funding Read Interface

MENDER consumes O2O funding state produced by:

    o2o/bin/grantkit-o2o-state

MENDER may:

- inspect proposal state
- classify proposal condition
- create coordination queues
- route research, writing, repair, and review work
- surface state to Paraclete and Commons
- preserve evidence through PNEUMA

MENDER may not:

- authorize submission
- submit a proposal
- create a governor decision
- represent GrantKit validation as approval
- mutate authority state

## Data flow

    GrantKit
        |
        v
    status.json
        |
        v
    grantkit-o2o-state
        |
        v
    o2o-funding-state.json
        |
        v
    MENDER read interface
        |
        +-- inspect
        +-- classify
        +-- queue
        +-- route
        |
        v
    Paraclete / Commons / PNEUMA

## Governance boundary

    MENDER != GOVERNOR
    MENDER_COORDINATION != AUTHORIZATION
    VALIDATED != APPROVED
    APPROVED != AUTHORIZED
    AUTHORIZED != SUBMITTED
    AGENT_OUTPUT != GOVERNOR_DECISION
    CONVERSATION != PERMIT

Defaults:

    MENDER_CAN_AUTHORIZE=FALSE
    MENDER_CAN_SUBMIT=FALSE
    AUTHORITY_CHANGED=FALSE
