# O2O GrantKit Adaptation

This directory contains the O2O-specific adaptation layer around GrantKit.

GrantKit remains the deterministic proposal compiler and validator.

O2O adds coordination, provenance, operational state, and governance boundaries
without treating validation as authorization.

## Core distinction

GRANTKIT_VALIDATED != PROPOSAL_APPROVED
PROPOSAL_APPROVED != SUBMISSION_AUTHORIZED
SUBMISSION_AUTHORIZED != SUBMITTED
SUBMITTED != AWARDED

## Roles

- GrantKit: deterministic validation and compilation
- MENDER: coordination and task routing
- Paraclete: human operating and review surface
- Commons: portfolio visibility
- PNEUMA: evidence, state, and custody
- Governance: authorization boundary

AUTHORITY_CHANGED=FALSE by default.
