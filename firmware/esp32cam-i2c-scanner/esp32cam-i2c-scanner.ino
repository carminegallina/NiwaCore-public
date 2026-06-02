/*
  NIWA ESP32-CAM I2C scanner

  Safe diagnostic firmware for the first Companion OLED test.

  Wiring:
  - OLED GND -> ESP32-CAM GND
  - OLED VCC -> ESP32-CAM 3V3
  - OLED SCL -> ESP32-CAM GPIO 14
  - OLED SDA -> ESP32-CAM GPIO 13
*/

#include <Wire.h>

const int I2C_SDA_PIN = 13;
const int I2C_SCL_PIN = 14;

void scanI2cBus() {
  int deviceCount = 0;

  Serial.println("Scansione bus I2C...");

  for (int address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    int error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Dispositivo I2C trovato a 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
      deviceCount++;
    }
  }

  if (deviceCount == 0) {
    Serial.println("Nessun dispositivo I2C trovato.");
  } else {
    Serial.print("Totale dispositivi I2C: ");
    Serial.println(deviceCount);
  }
}

void setup() {
  Serial.begin(115200);
  delay(800);

  Serial.println();
  Serial.println("NIWA ESP32-CAM scanner I2C avviato.");
  Serial.print("SDA GPIO ");
  Serial.print(I2C_SDA_PIN);
  Serial.print(", SCL GPIO ");
  Serial.println(I2C_SCL_PIN);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  scanI2cBus();
}

void loop() {
  delay(5000);
  scanI2cBus();
}
