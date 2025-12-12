#ifndef FORCE_FEEDBACK_H
#define FORCE_FEEDBACK_H

#include <Arduino.h>

extern const int pwm_threshold;
extern const int pwm_floor;
extern const int pwm_max;
extern const int pwm_min;

int proportionalControlBasic(float degrees, int acc, int brake, bool onlyWheel);

#endif
