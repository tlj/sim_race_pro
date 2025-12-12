#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <SoftwareSerial.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

const char *FW_VERSION = "ver. 1.0.0";

const char *HEADER_TEXT = "SIM RACE PRO";
const uint8_t HEADER_SIZE = 1;
const int16_t HEADER_Y = 6;
const int16_t HEADER_H = 8 * HEADER_SIZE;

const uint8_t rowPins[4] = {4, 5, 6, 7};
const uint8_t colPins[4] = {8, 9, 10, 11};

const uint8_t RESET_PIN = 12;

const uint8_t ledPins[3] = {A2, A1, A0};

SoftwareSerial link(2, 3);

int lastActive = -1;
unsigned long lastFrameMs = 0;

bool enableSerialTX = false;
bool enableSerialRX = true;

void scanMatrix(bool keyStates[16], uint8_t *firstPressed)
{
  *firstPressed = 0;
  for (uint8_t i = 0; i < 16; i++)
    keyStates[i] = false;

  for (uint8_t r = 0; r < 4; r++)
    pinMode(rowPins[r], INPUT);

  for (uint8_t r = 0; r < 4; r++)
  {
    pinMode(rowPins[r], OUTPUT);
    digitalWrite(rowPins[r], LOW);
    delayMicroseconds(5);

    for (uint8_t c = 0; c < 4; c++)
    {
      bool pressed = (digitalRead(colPins[c]) == LOW);
      uint8_t idx = r * 4 + c;
      if (pressed)
      {
        keyStates[idx] = true;
        if (*firstPressed == 0)
          *firstPressed = idx + 1;
      }
    }
    pinMode(rowPins[r], INPUT);
  }
}

void sendMatrixState(bool keyStates[16], bool resetPressed)
{
    for (uint8_t i = 0; i < 16; i++)
    {
      link.print(keyStates[i] ? '1' : '0');
      link.print('-');

      if (enableSerialTX)
      {
        Serial.print(keyStates[i] ? '1' : '0');
        Serial.print('-');
      }
    }

    link.println(resetPressed ? '1' : '0');

    if (enableSerialTX)
      Serial.print(resetPressed ? '1' : '0');
}

void setup()
{

  Serial.println("Starting Setup...");

  for (uint8_t i = 0; i < 3; i++)
  {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }

  pinMode(RESET_PIN, INPUT_PULLUP);

  for (uint8_t c = 0; c < 4; c++)
    pinMode(colPins[c], INPUT_PULLUP);
  for (uint8_t r = 0; r < 4; r++)
    pinMode(rowPins[r], INPUT);

  link.begin(9600);
  Serial.begin(9600);

  Wire.begin();
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("READY");
  display.display();
  delay(1000);

  lastActive = 0;

  Serial.println("Setup Complete.");
}

void loop()
{
  bool keyStates[16];
  uint8_t firstPressed = 0;
  scanMatrix(keyStates, &firstPressed);

  bool resetPressed = (digitalRead(RESET_PIN) == LOW);

  if (link.available())
  {
    static char rxBuf[48];
    static uint8_t rxLen = 0;

    static float lastDegrees = 0.0f;
    static int lastAcc = 0;
    static int lastBrk = 0;

    while (link.available())
    {
      char c = (char)link.read();

      if (c == '\n')
      {

        if (rxLen > 0 && rxBuf[rxLen - 1] == '\r')
          rxLen--;
        rxBuf[rxLen] = '\0';

        char *p1 = strtok(rxBuf, "-");
        char *p2 = strtok(NULL, "-");
        char *p3 = strtok(NULL, "-");
        char *p4 = strtok(NULL, "-");

        if (p1 && p2 && p3)
        {
          float degrees = atof(p1);
          int acc = constrain(atoi(p2), 0, 255);
          int brk = constrain(atoi(p3), 0, 255);

          lastDegrees = degrees;
          lastAcc = acc;
          lastBrk = brk;



          if (enableSerialRX)
          {
            if (enableSerialTX)
              Serial.print(" | ");

            Serial.print(degrees);
            Serial.print('-');
            Serial.print(acc);
            Serial.print('-');
            Serial.print(brk);
            Serial.print('-');
            Serial.println(p4);
          }

          // State variables to prevent flickering
          static char prev_gear[4] = "";
          static int prev_speed = -1;
          static int prev_rpm_pct = -1;
          static int prev_thr = -1;
          static int prev_brk = -1;
          static int prev_ang = -999;

          char current_gear[4] = "N";
          int current_speed = 0;
          int current_rpm_pct = 0;
          
          // Use data from Box (p1, p2, p3)
          int current_thr = map(acc, 0, 255, 0, 100);
          int current_brk = map(brk, 0, 255, 0, 100);
          int current_ang = (int)degrees;

          if (p4 && strcmp(p4, "NONE") != 0)
          {
            char *t_rpm = strtok(p4, ";");
            char *t_gear = strtok(NULL, ";");
            char *t_speed = strtok(NULL, ";");
            char *t_gx = strtok(NULL, ";");
            char *t_rumble = strtok(NULL, ";");
            char *t_rpm_pct = strtok(NULL, ";");

            if (t_rpm && t_gear && t_speed && t_rpm_pct)
            {
              strncpy(current_gear, t_gear, 3);
              current_gear[3] = '\0';
              current_speed = atoi(t_speed);
              current_rpm_pct = atoi(t_rpm_pct);
            }
          }

          // Only update display if something changed
          if (strcmp(current_gear, prev_gear) != 0 || 
              current_speed != prev_speed || 
              current_rpm_pct != prev_rpm_pct ||
              current_thr != prev_thr ||
              current_brk != prev_brk ||
              current_ang != prev_ang)
          {
              // Update previous values
              strcpy(prev_gear, current_gear);
              prev_speed = current_speed;
              prev_rpm_pct = current_rpm_pct;
              prev_thr = current_thr;
              prev_brk = current_brk;
              prev_ang = current_ang;

              // Update LEDs
              digitalWrite(ledPins[0], (current_rpm_pct >= 50) ? HIGH : LOW);
              digitalWrite(ledPins[1], (current_rpm_pct >= 75) ? HIGH : LOW);
              digitalWrite(ledPins[2], (current_rpm_pct >= 90) ? HIGH : LOW);

              // Draw Display
              display.clearDisplay();

              // Top Info Row
              display.setTextSize(1);
              
              // Brake (Top Left)
              display.setCursor(0, 0);
              display.print(current_brk);

              // Angle (Top Center)
              display.setCursor(54, 0);
              display.print(current_ang);

              // Throttle (Top Right)
              // Adjust cursor based on digits to align right
              int thr_x = 110;
              if(current_thr < 10) thr_x = 122;
              else if(current_thr < 100) thr_x = 116;
              display.setCursor(thr_x, 0);
              display.print(current_thr);

              // RPM Bar (Moved down)
              int barWidth = map(current_rpm_pct, 0, 100, 0, SCREEN_WIDTH);
              display.fillRect(0, 12, barWidth, 6, SSD1306_WHITE);

              // Gear (Large)
              display.setTextSize(5);
              display.setCursor(46, 24);
              display.print(current_gear);

              // Speed (Bottom)
              display.setTextSize(2);
              display.setCursor(0, 48);
              display.print(current_speed);
              display.setTextSize(1);
              display.print(" kmh");

              display.display();
          }

          sendMatrixState(keyStates, resetPressed);
        }

        rxLen = 0;
      }
      else
      {
        if (rxLen < sizeof(rxBuf) - 1)
          rxBuf[rxLen++] = c;
        else
          rxLen = 0;
      }
    }
  }
}
