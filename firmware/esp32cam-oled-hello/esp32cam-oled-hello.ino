/*
  NIWA Companion - OLED hello-world test

  Safe first screen test for AI Thinker ESP32-CAM boards and 128x64 SSD1306
  I2C OLED displays. No external Arduino libraries are required.

  Wiring:
  - OLED GND -> ESP32-CAM GND
  - OLED VCC -> ESP32-CAM 3V3
  - OLED SCL -> ESP32-CAM GPIO 14
  - OLED SDA -> ESP32-CAM GPIO 13

  Manual flash procedure for the current adapter:
  - Connect ESP32-CAM GPIO 0 to GND only while uploading.
  - Disconnect GPIO 0 from GND before restarting the board.
  - Press RST once to start the uploaded sketch.
*/

#include <Wire.h>

const int I2C_SDA_PIN = 13;
const int I2C_SCL_PIN = 14;
const int OLED_WIDTH = 128;
const int OLED_HEIGHT = 64;
const int OLED_BUFFER_SIZE = OLED_WIDTH * OLED_HEIGHT / 8;

uint8_t oledAddress = 0;
uint8_t frameBuffer[OLED_BUFFER_SIZE];

struct Glyph {
  char character;
  uint8_t columns[5];
};

const Glyph FONT[] = {
  {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
  {'?', {0x02, 0x01, 0x59, 0x09, 0x06}},
  {'A', {0x7E, 0x11, 0x11, 0x11, 0x7E}},
  {'D', {0x7F, 0x41, 0x41, 0x22, 0x1C}},
  {'E', {0x7F, 0x49, 0x49, 0x49, 0x41}},
  {'H', {0x7F, 0x08, 0x08, 0x08, 0x7F}},
  {'I', {0x00, 0x41, 0x7F, 0x41, 0x00}},
  {'L', {0x7F, 0x40, 0x40, 0x40, 0x40}},
  {'N', {0x7F, 0x02, 0x04, 0x08, 0x7F}},
  {'O', {0x3E, 0x41, 0x41, 0x41, 0x3E}},
  {'R', {0x7F, 0x09, 0x19, 0x29, 0x46}},
  {'W', {0x7F, 0x20, 0x18, 0x20, 0x7F}},
};

const uint8_t* glyphFor(char character) {
  for (const Glyph& glyph : FONT) {
    if (glyph.character == character) {
      return glyph.columns;
    }
  }
  return FONT[1].columns;
}

bool deviceAt(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void sendCommand(uint8_t command) {
  Wire.beginTransmission(oledAddress);
  Wire.write(0x00);
  Wire.write(command);
  Wire.endTransmission();
}

void initializeDisplay() {
  const uint8_t commands[] = {
    0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40,
    0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12,
    0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6,
    0xAF,
  };

  for (uint8_t command : commands) {
    sendCommand(command);
  }
}

void clearFrame() {
  for (int index = 0; index < OLED_BUFFER_SIZE; index++) {
    frameBuffer[index] = 0;
  }
}

void setPixel(int x, int y, bool enabled = true) {
  if (x < 0 || x >= OLED_WIDTH || y < 0 || y >= OLED_HEIGHT) {
    return;
  }

  int index = x + (y / 8) * OLED_WIDTH;
  uint8_t mask = 1 << (y & 7);
  if (enabled) {
    frameBuffer[index] |= mask;
  } else {
    frameBuffer[index] &= ~mask;
  }
}

void drawRect(int x, int y, int width, int height) {
  for (int offset = 0; offset < width; offset++) {
    setPixel(x + offset, y);
    setPixel(x + offset, y + height - 1);
  }
  for (int offset = 0; offset < height; offset++) {
    setPixel(x, y + offset);
    setPixel(x + width - 1, y + offset);
  }
}

void drawChar(int x, int y, char character, int scale = 1) {
  const uint8_t* columns = glyphFor(character);

  for (int column = 0; column < 5; column++) {
    for (int row = 0; row < 7; row++) {
      if ((columns[column] & (1 << row)) == 0) {
        continue;
      }
      for (int dx = 0; dx < scale; dx++) {
        for (int dy = 0; dy < scale; dy++) {
          setPixel(x + column * scale + dx, y + row * scale + dy);
        }
      }
    }
  }
}

void drawText(int x, int y, const char* text, int scale = 1) {
  while (*text) {
    drawChar(x, y, *text, scale);
    x += 6 * scale;
    text++;
  }
}

void drawFilledRect(int x, int y, int width, int height) {
  for (int dx = 0; dx < width; dx++) {
    for (int dy = 0; dy < height; dy++) {
      setPixel(x + dx, y + dy);
    }
  }
}

void sendFrame() {
  sendCommand(0x21);
  sendCommand(0);
  sendCommand(OLED_WIDTH - 1);
  sendCommand(0x22);
  sendCommand(0);
  sendCommand((OLED_HEIGHT / 8) - 1);

  for (int start = 0; start < OLED_BUFFER_SIZE; start += 16) {
    Wire.beginTransmission(oledAddress);
    Wire.write(0x40);
    for (int offset = 0; offset < 16; offset++) {
      Wire.write(frameBuffer[start + offset]);
    }
    Wire.endTransmission();
  }
}

void drawHelloScreen() {
  clearFrame();
  drawRect(0, 0, OLED_WIDTH, OLED_HEIGHT);
  drawText(52, 5, "NIWA", 1);
  drawFilledRect(23, 15, 8, 8);
  drawFilledRect(97, 15, 8, 8);
  drawText(34, 29, "HELLO", 2);
  drawText(34, 46, "WORLD", 2);
  sendFrame();
}

void setup() {
  Serial.begin(115200);
  delay(800);

  Serial.println();
  Serial.println("NIWA Companion OLED hello-world avviato.");
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  if (deviceAt(0x3C)) {
    oledAddress = 0x3C;
  } else if (deviceAt(0x3D)) {
    oledAddress = 0x3D;
  } else {
    Serial.println("OLED non trovato a 0x3C o 0x3D.");
    return;
  }

  Serial.print("OLED trovato a 0x");
  Serial.println(oledAddress, HEX);

  initializeDisplay();
  drawHelloScreen();
  Serial.println("HELLO WORLD inviato al display.");
}

void loop() {
  delay(5000);
  if (oledAddress != 0) {
    Serial.println("NIWA Companion display online.");
  }
}
