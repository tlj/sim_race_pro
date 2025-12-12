#include "force_feedback.h"
#include "motor_control.h"

const int pwm_threshold = 5;
const int pwm_floor = 15;
const int pwm_max = 255;
const int pwm_min = 60;

int proportionalControlBasic(float degrees, int acc, int brake, bool onlyWheel)
{
  int pwm = 0;

  if (degrees >= 450.0f || degrees <= -450.0f)
  {
    stopMotor();
    disableMotor();
    return 0;
  }
  else
  {
    enableMotor();
  }

  int effort = (brake > 0) ? brake : (acc > 0 ? acc : 0);

  if (onlyWheel)
    effort = 255;

  if (effort > 0)
  {
    if (degrees >= pwm_threshold)
    {
      long angle = (long)degrees;
      long prod = angle * (long)effort;
      pwm = map(prod, 0L, 114750L, pwm_min, pwm_max);
      if (pwm > 0 && pwm < pwm_floor)
        pwm = pwm_floor;
      moveMotorToLeft(pwm);
    }
    else if (degrees <= -pwm_threshold)
    {
      long angle = (long)(-degrees);
      long prod = angle * (long)effort;
      pwm = map(prod, 0L, 114750L, pwm_min, pwm_max);
      if (pwm > 0 && pwm < pwm_floor)
        pwm = pwm_floor;
      moveMotorToRight(pwm);
    }
    else
    {
      stopMotor();
      pwm = 0;
    }
  }
  else
  {
    stopMotor();
    pwm = 0;
  }

  return pwm;
}
