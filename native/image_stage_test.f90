program image_stage_test
  use, intrinsic :: iso_c_binding, only: c_bool, c_double, c_int
  use arach_image_stage, only: image_stage_score, installer_stage_admitted
  implicit none
  real(c_double) :: rejected
  real(c_double) :: boot
  real(c_double) :: desktop
  logical(c_bool) :: installer_ok
  logical(c_bool) :: installer_without_journal

  rejected = image_stage_score(100.0_c_double, 100_c_int, 0.0_c_double, &
                               .false._c_bool)
  boot = image_stage_score(4.0_c_double, 10_c_int, 2.0_c_double, .true._c_bool)
  desktop = image_stage_score(2.0_c_double, 2_c_int, 4.0_c_double, .true._c_bool)
  installer_ok = installer_stage_admitted(.true._c_bool, .true._c_bool, &
                                           .true._c_bool, .true._c_bool)
  installer_without_journal = installer_stage_admitted(.false._c_bool, &
                                                        .true._c_bool, &
                                                        .true._c_bool, &
                                                        .true._c_bool)

  if (abs(rejected + 1.0_c_double) > epsilon(rejected)) error stop 1
  if (boot <= desktop) error stop 2
  if (.not. installer_ok) error stop 3
  if (installer_without_journal) error stop 4
end program image_stage_test
