# O2O GrantKit Architecture

GrantKit
  |
  +-- deterministic validation
  +-- compilation
  +-- status.json
  |
  v
O2O Adaptation Layer
  |
  +-- MENDER coordination
  +-- PNEUMA evidence/state
  +-- Paraclete review surface
  +-- Commons portfolio visibility
  +-- Governance authorization boundary

GrantKit's `status.json` remains the canonical proposal-state interface.

O2O governance state lives separately in `o2o-funding-state.json`.

This prevents proposal validation from being mistaken for operational authority.
