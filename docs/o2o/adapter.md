# O2O GrantKit State Adapter

`o2o/bin/grantkit-o2o-state` is the O2O bridge between GrantKit proposal
state and O2O funding governance state.

It runs the real GrantKit status engine and consumes the resulting
`status.json`.

It does not modify GrantKit's status contract.

Instead it writes a sibling artifact:

    o2o-funding-state.json

## Usage

    o2o/bin/grantkit-o2o-state /path/to/grant

An explicit GrantKit executable can be supplied:

    o2o/bin/grantkit-o2o-state \
      /path/to/grant \
      --grantkit /path/to/grantkit

## Truth boundary

The adapter preserves these distinctions:

    VALIDATED != APPROVED
    APPROVED != AUTHORIZED
    AUTHORIZED != SUBMITTED
    SUBMITTED != AWARDED

The following governance fields are always false in this adapter:

    proposal_approved
    submission_authorized
    submission_observed
    award_observed

The following authority field is always false:

    authority.changed

A separate authorized governance process must establish any future
transition beyond these defaults.

## Failure behavior

The adapter fails closed.

If:

- GrantKit cannot run
- `grant.yaml` does not exist
- `status.json` is not produced
- `status.json` is invalid
- the expected status contract is incomplete

then no successful O2O state transition is reported.

GrantKit validation state is evidence.

It is not authorization.
