# Funding Observation Binding

Historical PNEUMA funding observations may predate stable proposal
identities.

A binding record explicitly associates one observation bundle with one
stable proposal identity.

Bindings are separate evidence records.

They do not rewrite the original observation and do not rewrite the
identity registry.

## Required evidence

A binding requires:

- observation bundle ID
- stable proposal ID
- evidence source
- binding rationale
- confidence level

The binding tool does not infer identity from titles.

## Structure

    funding/bindings/
      records/
        BIND-*.json
      bindings.jsonl

## Truth boundary

    BINDING != AUTHORIZATION
    BINDING != SUBMISSION
    BINDING != EXECUTION
    OBSERVATION != PROPOSAL

Bindings may:

- connect evidence to stable proposal identity
- preserve evidence source
- preserve rationale
- preserve confidence
- support identity-aware Commons grouping

Bindings may not:

- authorize submission
- establish execution
- mutate prior observation bundles
- mutate proposal identities
- change governor authority

Defaults:

    BINDING_IS_AUTHORIZATION=FALSE
    BINDING_IS_SUBMISSION=FALSE
    BINDING_IS_EXECUTION=FALSE
    OBSERVATION_MUTATED=FALSE
    IDENTITY_RECORD_MUTATED=FALSE
    AUTHORITY_CHANGED=FALSE
