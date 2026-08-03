# Package semantics gate

This gate defines required package graph semantics beyond native package installation.

## Required semantics

1. replacements and conflicts
2. optional/feature dependencies
3. split packages and devel/debug artifacts
4. multilib routing
5. configuration-file merge behavior
6. ownership and permission policy (users/groups, modes, xattrs, ACLs)
7. safe symlink/hardlink behavior
8. file capabilities and privilege tags
9. service declarations and lifecycle order
10. desktop registration and trigger semantics

## Evidence expectations

- manifests prove each transition preserves intended ownership and capability model
- destructive conflict cases are explicitly tested
- route selection and fallback are reproducible and auditable

## Current status

`in_progress`  
Semantics checklist captured for implementation planning and test synthesis.
