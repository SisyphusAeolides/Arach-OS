module arach_image_stage
  use, intrinsic :: iso_c_binding, only: c_bool, c_double, c_int
  implicit none
  private
  public :: image_stage_score, installer_stage_admitted
contains
  function image_stage_score(phase_weight, dependents, memory_gib, &
                             trust_admitted) result(score) bind(C)
    real(c_double), value :: phase_weight
    integer(c_int), value :: dependents
    real(c_double), value :: memory_gib
    logical(c_bool), value :: trust_admitted
    real(c_double) :: score

    if (.not. trust_admitted) then
      score = -1.0_c_double
      return
    end if
    score = max(phase_weight, 0.0_c_double) * 16.0_c_double &
          + real(max(dependents, 0_c_int), c_double) * 2.0_c_double &
          - max(memory_gib, 0.0_c_double) * 0.25_c_double
  end function image_stage_score

  function installer_stage_admitted(journal_durable, secrets_excluded, &
                                    shell_free, rollback_defined) result(admitted) bind(C)
    logical(c_bool), value :: journal_durable
    logical(c_bool), value :: secrets_excluded
    logical(c_bool), value :: shell_free
    logical(c_bool), value :: rollback_defined
    logical(c_bool) :: admitted

    admitted = journal_durable .and. secrets_excluded .and. shell_free .and. rollback_defined
  end function installer_stage_admitted
end module arach_image_stage
