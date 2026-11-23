"""Enforcer 1 and the emitters, all from one declaration per module (FS-002 5.3).

`api.domain.authz` holds the pure half: the ScopeSpec and the matrix parser.
`modules` holds the declarations. `policy_sql` emits the policies and indexes a
migration pastes in. `predicate` builds the service-layer clause and the stage-4
parent lookup. The parity suite is what proves the emitters agree.
"""
