#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/arach-os-fortran.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT

gfortran -std=f2018 -Wall -Wextra -Werror \
    -J "$scratch" \
    "$root/native/image_stage.f90" \
    "$root/native/image_stage_test.f90" \
    -o "$scratch/image-stage-test"
"$scratch/image-stage-test"
