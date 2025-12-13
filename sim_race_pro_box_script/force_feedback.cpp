#include "force_feedback.h"
#include "motor_control.h"

const int pwm_threshold = 5;
const int pwm_floor = 15;
const int pwm_max = 255;
const int pwm_min = 60;

int proportionalControlBasic(float degrees, int acc, int brake, int speed, int gx, int rumble, bool onlyWheel)
{
  int pwm = 0;

  if (degrees >= 450.0f || degrees <= -450.0f) {
    stopMotor();
    disableMotor();
    return 0;
  } else {
    enableMotor();
  }

  // 1. Legacy Input Effort (Pedals)
  int base_effort = (brake > 0) ? brake : (acc > 0 ? acc : 0);
  if (onlyWheel) base_effort = 255;

  // 2. Sim Input Effort (Telemetry)
  int sim_effort = 0;
  
  // Speed Loading (Stiffer at speed)
  if (speed > 0) {
      sim_effort += map(constrain(speed, 0, 300), 0, 300, 60, 220); // Stronger at speed (max 220/255)
  }
  
  // G-Force Loading (Stiffer in corners)
  int g_mag = abs(gx - 127);
  if (g_mag > 5) {
      sim_effort += map(constrain(g_mag, 0, 127), 0, 127, 0, 120); // More resistance in corners
  }

  // Rumble (Curbs) -> Direct force injection
  if (rumble > 0) {
      sim_effort += rumble; 
  }

  // 3. Combine: Take the strongest requested force
  int total_effort = 0;
  if (base_effort > sim_effort) total_effort = base_effort;
  else total_effort = sim_effort;
  
  total_effort = constrain(total_effort, 0, 255);

  if (total_effort > 0)
  {
    if (degrees >= pwm_threshold)
    {
      long angle = (long)degrees;
      long prod = angle * (long)total_effort;
      pwm = map(prod, 0L, 114750L, pwm_min, pwm_max);
      if (pwm > 0 && pwm < pwm_floor) pwm = pwm_floor;
      moveMotorToLeft(pwm);
    }
    else if (degrees <= -pwm_threshold)
    {
      long angle = (long)(-degrees);
      long prod = angle * (long)total_effort;
      pwm = map(prod, 0L, 114750L, pwm_min, pwm_max);
      if (pwm > 0 && pwm < pwm_floor) pwm = pwm_floor;
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
