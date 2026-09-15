# PNEUMA Funding Identity Registry

The PNEUMA funding identity registry stores normalized project,
proposal, candidate, and reusable-source identities.

It separates identity from observation and authority.

## Structure

    funding/identity/
      projects/
      proposals/
      candidates/
      source-library/
      relationships.jsonl
      registry.json

## Identity distinctions

    PROJECT != PROPOSAL
    PROPOSAL != OBSERVATION
    OBSERVATION != AUTHORIZATION
    AGGREGATE_TARGET != PROPOSAL_REQUEST

## Governance

The registry may preserve:

- stable project identities
- proposal identities
- proposal candidates
- reusable source records
- project/proposal relationships

The registry may not:

- authorize submission
- submit proposals
- claim execution
- mutate prior PNEUMA observations
- change governor authority

Defaults:

    REGISTRY_IS_AUTHORIZATION=FALSE
    PROJECT_IDENTITY_IS_AUTHORIZATION=FALSE
    PROPOSAL_IDENTITY_IS_AUTHORIZATION=FALSE
    HISTORY_IS_EXECUTION=FALSE
    SUBMISSION_AUTHORIZED=FALSE
    AUTHORITY_CHANGED=FALSE
