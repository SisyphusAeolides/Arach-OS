# Universal route statement gate

Every workload must terminate in one explicit execution route:

1. native
2. rebuilt
3. compatibility runtime
4. container
5. managed VM

## Requirements

- each non-native package gets an explicit route label
- route decisions remain user-visible and auditable
- unsupported workloads fail predictably with documented remediation
- route transitions are tested by representative workloads

## Current status

`done`  
Route statement is formalized and wired into package metadata.
