#include "motor_control.h"

const int RPWM = 11;
const int LPWM = 10;
const int REN = 9;
const int LEN = 8;

void setupMotor() {
    pinMode(RPWM, OUTPUT);
    pinMode(LPWM, OUTPUT);
    pinMode(REN, OUTPUT);
    pinMode(LEN, OUTPUT);

    TCCR1B = (TCCR1B & 0b11111000) | 0x01;
    TCCR2B = (TCCR2B & 0b11111000) | 0x01;

    enableMotor();
}

void moveMotorToLeft(int vel)
{
  analogWrite(RPWM, vel);
  analogWrite(LPWM, 0);
}

void moveMotorToRight(int vel)
{
  analogWrite(RPWM, 0);
  analogWrite(LPWM, vel);
}

void stopMotor()
{
  analogWrite(RPWM, 0);
  analogWrite(LPWM, 0);
}

void enableMotor()
{
  digitalWrite(REN, HIGH);
  digitalWrite(LEN, HIGH);
}

void disableMotor()
{
  digitalWrite(REN, LOW);
  digitalWrite(LEN, LOW);
}
