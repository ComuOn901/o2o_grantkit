# O2O Funding Constitution

## Purpose

GrantKit provides deterministic proposal validation and compilation.

The O2O adaptation layer MUST NOT convert validation results into authority.

## Invariants

- VALIDATED != APPROVED
- APPROVED != AUTHORIZED
- AUTHORIZED != SUBMITTED
- SUBMITTED != AWARDED
- AGENT_OUTPUT != GOVERNOR_DECISION
- CONVERSATION != PERMIT

## GrantKit may

- scaffold proposal structures
- validate funder constraints
- check citations
- check budget arithmetic
- produce structured review artifacts
- compile proposal artifacts
- expose machine-readable proposal state

## GrantKit may not

- authorize submission
- commit organizational funds
- sign attestations
- promise matching funds
- fabricate funder requirements
- treat AI output as governance approval

## MUNDER may

- coordinate proposal work
- inspect GrantKit status
- request revisions
- route research and writing tasks
- assemble review queues

## MUNDER may not

- self-authorize submission
- create financial commitments
- treat validation success as approval

Default operational state:

AUTHORITY_CHANGED=FALSE
SUBMISSION_AUTHORIZED=FALSE
SUBMITTED=FALSE
AWARDED=FALSE
