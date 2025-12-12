#include <SoftwareSerial.h>
#include <Encoder.h>
#include "motor_control.h"
#include "force_feedback.h"

const char *FW_VERSION = "ver. 1.1.0";

enum SIM_SETUP
{
  BOX_FULL,
  BOX_MEDIUM,
  BOX_BUDGET
};

SIM_SETUP sim_setup = BOX_FULL;

bool ONLY_WHEEL = false;

bool PEDALS_CLUTCH = false;

bool HANDBRAKE_ENABLED = false;
bool MANUAL_TX_ENABLED = false;

bool PEDALS_VIBRATION_ENABLED = false;

SoftwareSerial link(5, 6);

Encoder myEnc(2, 3);
const long maxTicks = 3000;
long zeroOffset = 0;

const uint8_t ACC_PIN = A0;
const uint8_t BRK_PIN = A1;
int ACC_OFFSET = 0;
int BRK_OFFSET = 0;
int POT_OFFSET = 0;
int ACC_DEADZONE = 10;
int BRK_DEADZONE = 10;
int ACC_INPUT_MAX = 90;
int BRK_INPUT_MAX = 90;

const uint8_t VIB_PIN = A2;
const uint8_t VIB2_PIN = A3;

const int POT_PIN = A4;

const int CLUTCH_PIN = A3;

const int HANDBRAKE_PIN = 4;
const int MANUAL_TX_POT1_PIN = A7;
const int MANUAL_TX_POT2_PIN = A6;

char lineBuf[96];
uint8_t lineLen = 0;
bool lastResetBit = false;

const byte MAX_CHARS = 64;

char pcBuffer[MAX_CHARS];
byte pcIndex = 0;
bool pcMsgReady = false;

char slaveRxBuffer[MAX_CHARS];
byte slaveIndex = 0;
bool slaveMsgReady = false;

char slaveBuffer[MAX_CHARS];

bool extractResetBit(const char *s)
{
  int len = 0;
  while (s[len] != '\0')
    len++;
  for (int i = len - 1; i >= 0; --i)
  {
    if (s[i] == '0')
      return false;
    if (s[i] == '1')
      return true;
  }
  return false;
}

bool isValidMessage(const char *msg)
{
  int semiCount = 0;
  int len = 0;
  while (msg[len] != '\0')
  {
    if (msg[len] == ';')
      semiCount++;
    len++;
    if (len > MAX_CHARS)
      return false;
  }
  return (semiCount == 4);
}

char readHandbrakeBit()
{
  int v = digitalRead(HANDBRAKE_PIN);
  return (v == LOW) ? '1' : '0';
}

void setup()
{
  Serial.begin(9600);
  link.begin(9600);

  strcpy(slaveBuffer, "WAIT");

  if (sim_setup == BOX_FULL)
  {
    setupMotor();
  }

  if (sim_setup == BOX_FULL || sim_setup == BOX_MEDIUM)
  {
    zeroOffset = myEnc.read();
  }

  if (sim_setup == BOX_BUDGET)
  {
    pinMode(POT_PIN, INPUT);
  }

  if (ONLY_WHEEL == false)
  {
    pinMode(ACC_PIN, INPUT);
    pinMode(BRK_PIN, INPUT);
    ACC_OFFSET = analogRead(ACC_PIN);
    BRK_OFFSET = analogRead(BRK_PIN);

    if (PEDALS_CLUTCH == true)
    {
      pinMode(CLUTCH_PIN, INPUT);
    }
  }

  if (HANDBRAKE_ENABLED)
  {
    pinMode(HANDBRAKE_PIN, INPUT_PULLUP);
  }

  if (MANUAL_TX_ENABLED)
  {
    pinMode(MANUAL_TX_POT1_PIN, INPUT);
    pinMode(MANUAL_TX_POT2_PIN, INPUT);
  }

  if (PEDALS_VIBRATION_ENABLED)
  {
    pinMode(VIB_PIN, OUTPUT);
    pinMode(VIB2_PIN, OUTPUT);
  }
}

void loop()
{
  readSerialData(Serial, pcBuffer, pcIndex, pcMsgReady);
  readSerialData(link, slaveRxBuffer, slaveIndex, slaveMsgReady);

  if (slaveMsgReady)
  {
    if (isValidMessage(slaveRxBuffer))
    {
      strcpy(slaveBuffer, slaveRxBuffer);
    }

    bool resetBit = extractResetBit(slaveBuffer);
    if (resetBit && !lastResetBit)
    {
      zeroOffset = (sim_setup != BOX_BUDGET) ? myEnc.read() : 0;
      ACC_OFFSET = (!ONLY_WHEEL) ? analogRead(ACC_PIN) : 0;
      BRK_OFFSET = (!ONLY_WHEEL) ? analogRead(BRK_PIN) : 0;
    }
    lastResetBit = resetBit;
    slaveMsgReady = false;
    slaveIndex = 0;
  }

  long ticks = (sim_setup != BOX_BUDGET) ? constrain(myEnc.read() - zeroOffset, -maxTicks, maxTicks) : 0;
  float degrees = (sim_setup != BOX_BUDGET) ? (ticks / 2400.0f) * 360.0f : 0.0f;

  int acc = abs(analogRead(ACC_PIN) - ACC_OFFSET);
  int brk = abs(analogRead(BRK_PIN) - BRK_OFFSET);

  acc = constrain(map(acc, 0, ACC_INPUT_MAX, 0, 255), 0, 255);
  brk = constrain(map(brk, 0, BRK_INPUT_MAX, 0, 255), 0, 255);
  acc = (acc < ACC_DEADZONE || ONLY_WHEEL) ? 0 : acc;
  brk = (brk < BRK_DEADZONE || ONLY_WHEEL) ? 0 : brk;

  proportionalControlBasic(degrees, acc, brk, ONLY_WHEEL);

  static unsigned long lastTx = 0;
  if (millis() - lastTx >= 70)
  {
    lastTx = millis();

    char hbBit = (HANDBRAKE_ENABLED) ? readHandbrakeBit() : '0';
    int gx255 = (MANUAL_TX_ENABLED) ? map(analogRead(MANUAL_TX_POT1_PIN), 0, 1023, 0, 255) : 0;
    int gy255 = (MANUAL_TX_ENABLED) ? map(analogRead(MANUAL_TX_POT2_PIN), 0, 1023, 0, 255) : 0;

    Serial.print(degrees, 1);
    Serial.print('-');
    Serial.print(acc);
    Serial.print('-');
    Serial.print(brk);
    Serial.print('-');
    Serial.print(slaveBuffer);
    Serial.print('-');
    Serial.print(hbBit);
    Serial.print('-');
    Serial.print(gx255);
    Serial.print('-');
    Serial.println(gy255);

    link.print(degrees, 1);
    link.print('-');
    link.print(acc);
    link.print('-');
    link.print(brk);
    link.print('-');

    if (pcMsgReady)
    {
      link.println(pcBuffer);
      pcMsgReady = false;
      pcIndex = 0;
    }
    else
    {
      link.println("NONE");
    }
  }
}

void readSerialData(Stream &source, char *buffer, byte &idx, bool &isReady)
{
  while (source.available() > 0 && !isReady)
  {
    char rc = source.read();

    if (rc == '\n')
    {
      buffer[idx] = '\0';
      isReady = true;
      idx = 0;
    }

    else if (rc != '\r')
    {
      if (idx < MAX_CHARS - 1)
      {
        buffer[idx] = rc;
        idx++;
      }
    }
  }
}
