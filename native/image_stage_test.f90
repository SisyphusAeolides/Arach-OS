program image_stage_test
  use, intrinsic :: iso_c_binding, only: c_bool, c_double, c_int
  use arach_image_stage, only: image_stage_score
  implicit none
  real(c_double) :: rejected
  real(c_double) :: boot
  real(c_double) :: desktop

  rejected = image_stage_score(100.0_c_double, 100_c_int, 0.0_c_double, &
                               .false._c_bool)
  boot = image_stage_score(4.0_c_double, 10_c_int, 2.0_c_double, .true._c_bool)
  desktop = image_stage_score(2.0_c_double, 2_c_int, 4.0_c_double, .true._c_bool)

  if (abs(rejected + 1.0_c_double) > epsilon(rejected)) error stop 1
  if (boot <= desktop) error stop 2
end program image_stage_test
