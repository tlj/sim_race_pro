#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <Arduino.h>

extern const int RPWM;
extern const int LPWM;
extern const int REN;
extern const int LEN;

void setupMotor();
void moveMotorToLeft(int vel);
void moveMotorToRight(int vel);
void stopMotor();
void enableMotor();
void disableMotor();

#endif
