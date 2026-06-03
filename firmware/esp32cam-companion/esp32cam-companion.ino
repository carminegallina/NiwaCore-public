/*
  NIWA Companion - animated OLED avatar

  ESP32-CAM remains a lightweight avatar node. The Raspberry panel owns the
  selected expression and the ESP32 renders it locally without camera or AI.

  OLED wiring:
  - OLED GND -> ESP32-CAM GND
  - OLED VCC -> ESP32-CAM 3V3
  - OLED SCL -> ESP32-CAM GPIO 14
  - OLED SDA -> ESP32-CAM GPIO 13

  Current adapter flash procedure:
  - Connect ESP32-CAM GPIO 0 to GND only while uploading.
  - Disconnect USB, remove GPIO 0 from GND, reconnect USB and press RST.

  Serial provisioning commands:
  - WIFI_SSID=<network>
  - WIFI_PASSWORD=<password>
  - SERVER_URL=http://10.42.0.1:5058
  - SAVE_WIFI
  - CLEAR_WIFI
  - STATUS

  Optional local build config:
  - create niwa_companion_local_config.h next to this sketch
  - the file is ignored by Git and may contain local Wi-Fi credentials
*/

#include <HTTPClient.h>
#include <FS.h>
#include <Preferences.h>
#include <SD_MMC.h>
#include <WiFi.h>
#include <Wire.h>
#include <esp_camera.h>
#include <esp_wifi.h>

#if __has_include("niwa_companion_local_config.h")
#include "niwa_companion_local_config.h"
#define NIWA_COMPANION_HAS_LOCAL_CONFIG 1
#else
#define NIWA_COMPANION_HAS_LOCAL_CONFIG 0
#endif

#ifndef NIWA_COMPANION_USE_LOCAL_WIFI
#define NIWA_COMPANION_USE_LOCAL_WIFI 0
#endif

#ifndef NIWA_COMPANION_WIFI_SSID
#define NIWA_COMPANION_WIFI_SSID ""
#endif

#ifndef NIWA_COMPANION_WIFI_PASSWORD
#define NIWA_COMPANION_WIFI_PASSWORD ""
#endif

#ifndef NIWA_COMPANION_SERVER_URL
#define NIWA_COMPANION_SERVER_URL "http://10.42.0.1:5058"
#endif

#include "companion_oled_bitmaps.h"

const char* FIRMWARE_VERSION = "0.4.0-camera-capture";
const char* DEVICE_ID = "companion_01";
const char* DEVICE_NAME = "NIWA Companion 01";
const char* DEVICE_HOSTNAME = "niwa-companion-01";
const char* DEFAULT_SERVER_URL = NIWA_COMPANION_SERVER_URL;
const char* LOCAL_WIFI_SSID = NIWA_COMPANION_WIFI_SSID;
const char* LOCAL_WIFI_PASSWORD = NIWA_COMPANION_WIFI_PASSWORD;
const char* LOCAL_SERVER_URL = NIWA_COMPANION_SERVER_URL;

const int I2C_SDA_PIN = 13;
const int I2C_SCL_PIN = 14;
const int CAMERA_PWDN_PIN = 32;
const int CAMERA_RESET_PIN = -1;
const int CAMERA_XCLK_PIN = 0;
const int CAMERA_SIOD_PIN = 26;
const int CAMERA_SIOC_PIN = 27;
const int CAMERA_Y9_PIN = 35;
const int CAMERA_Y8_PIN = 34;
const int CAMERA_Y7_PIN = 39;
const int CAMERA_Y6_PIN = 36;
const int CAMERA_Y5_PIN = 21;
const int CAMERA_Y4_PIN = 19;
const int CAMERA_Y3_PIN = 18;
const int CAMERA_Y2_PIN = 5;
const int CAMERA_VSYNC_PIN = 25;
const int CAMERA_HREF_PIN = 23;
const int CAMERA_PCLK_PIN = 22;
const int OLED_WIDTH = 128;
const int OLED_HEIGHT = 64;
const int OLED_BUFFER_SIZE = OLED_WIDTH * OLED_HEIGHT / 8;
const unsigned long FRAME_INTERVAL_MS = 55;
const unsigned long POLL_INTERVAL_MS = 950;
const unsigned long HEARTBEAT_INTERVAL_MS = 10000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 12000;
const unsigned long WIFI_ATTEMPT_TIMEOUT_MS = 22000;

uint8_t oledAddress = 0;
uint8_t frameBuffer[OLED_BUFFER_SIZE];
Preferences preferences;
String wifiSsid;
String wifiPassword;
String serverUrl = DEFAULT_SERVER_URL;
String serialLine;
String activeExpression = "idle";
String targetExpression = "idle";
String wifiConfigSource = "none";
String wifiStateLabel = "BOOT";
String serverStateLabel = "SERVER WAIT";
String cameraStateLabel = "not-tested";
String sdStateLabel = "not-tested";
String lastCaptureStatus = "none";
String lastCaptureFilename = "";
String lastHandledCommandId = "";
int remoteRevision = 0;
int lastWifiReason = 0;
int lastWifiChannel = 0;
int lastWifiRssi = 0;
int lastHttpStatus = 0;
int transitionPhase = 0;
float eyeOpenAmount = 1.0;
unsigned long lastFrameAt = 0;
unsigned long lastPollAt = 0;
unsigned long lastHeartbeatAt = 0;
unsigned long lastWifiRetryAt = 0;
unsigned long wifiAttemptStartedAt = 0;
unsigned long lastServerOkAt = 0;
bool wifiAttemptInProgress = false;
bool serverOnline = false;
bool cameraOnline = false;
bool sdOnline = false;
bool captureBusy = false;

void markServerStatus(bool online, int statusCode);

struct Glyph {
  char character;
  uint8_t columns[5];
};

const Glyph FONT[] = {
  {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
  {'!', {0x00, 0x00, 0x5F, 0x00, 0x00}},
  {'-', {0x08, 0x08, 0x08, 0x08, 0x08}},
  {'?', {0x02, 0x01, 0x51, 0x09, 0x06}},
  {'0', {0x3E, 0x51, 0x49, 0x45, 0x3E}},
  {'1', {0x00, 0x42, 0x7F, 0x40, 0x00}},
  {'2', {0x42, 0x61, 0x51, 0x49, 0x46}},
  {'3', {0x21, 0x41, 0x45, 0x4B, 0x31}},
  {'4', {0x18, 0x14, 0x12, 0x7F, 0x10}},
  {'5', {0x27, 0x45, 0x45, 0x45, 0x39}},
  {'6', {0x3C, 0x4A, 0x49, 0x49, 0x30}},
  {'7', {0x01, 0x71, 0x09, 0x05, 0x03}},
  {'8', {0x36, 0x49, 0x49, 0x49, 0x36}},
  {'9', {0x06, 0x49, 0x49, 0x29, 0x1E}},
  {'A', {0x7E, 0x11, 0x11, 0x11, 0x7E}},
  {'B', {0x7F, 0x49, 0x49, 0x49, 0x36}},
  {'C', {0x3E, 0x41, 0x41, 0x41, 0x22}},
  {'D', {0x7F, 0x41, 0x41, 0x22, 0x1C}},
  {'E', {0x7F, 0x49, 0x49, 0x49, 0x41}},
  {'F', {0x7F, 0x09, 0x09, 0x09, 0x01}},
  {'G', {0x3E, 0x41, 0x49, 0x49, 0x7A}},
  {'H', {0x7F, 0x08, 0x08, 0x08, 0x7F}},
  {'I', {0x00, 0x41, 0x7F, 0x41, 0x00}},
  {'K', {0x7F, 0x08, 0x14, 0x22, 0x41}},
  {'L', {0x7F, 0x40, 0x40, 0x40, 0x40}},
  {'M', {0x7F, 0x02, 0x0C, 0x02, 0x7F}},
  {'N', {0x7F, 0x02, 0x04, 0x08, 0x7F}},
  {'O', {0x3E, 0x41, 0x41, 0x41, 0x3E}},
  {'P', {0x7F, 0x09, 0x09, 0x09, 0x06}},
  {'R', {0x7F, 0x09, 0x19, 0x29, 0x46}},
  {'S', {0x46, 0x49, 0x49, 0x49, 0x31}},
  {'T', {0x01, 0x01, 0x7F, 0x01, 0x01}},
  {'U', {0x3F, 0x40, 0x40, 0x40, 0x3F}},
  {'V', {0x1F, 0x20, 0x40, 0x20, 0x1F}},
  {'W', {0x7F, 0x20, 0x18, 0x20, 0x7F}},
  {'Y', {0x07, 0x08, 0x70, 0x08, 0x07}},
  {'Z', {0x61, 0x51, 0x49, 0x45, 0x43}},
};

struct PixelSprite {
  const char* const* rows;
  uint8_t height;
};

const char* const SPRITE_ROUND_EYE_ROWS[] = {
  "   #######   ",
  "  #########  ",
  " ########### ",
  "#############",
  "#############",
  "#############",
  "#############",
  "#############",
  "#############",
  " ########### ",
  "  #########  ",
  "   #######   ",
};
const PixelSprite SPRITE_ROUND_EYE = {SPRITE_ROUND_EYE_ROWS, 12};

const char* const SPRITE_DOME_EYE_ROWS[] = {
  "    #####    ",
  "  #########  ",
  " ########### ",
  "#############",
  "#############",
  "#############",
  " ########### ",
  "  #### ####  ",
};
const PixelSprite SPRITE_DOME_EYE = {SPRITE_DOME_EYE_ROWS, 8};

const char* const SPRITE_CHEVRON_ROWS[] = {
  "##           ",
  " ###         ",
  "  ###        ",
  "   ###       ",
  "    ###      ",
  "   ###       ",
  "  ###        ",
  " ###         ",
  "##           ",
};
const PixelSprite SPRITE_CHEVRON = {SPRITE_CHEVRON_ROWS, 9};

const char* const SPRITE_ARC_EYE_ROWS[] = {
  "     ###     ",
  "   ##   ##   ",
  "  ##     ##  ",
  " ##       ## ",
  "##         ##",
};
const PixelSprite SPRITE_ARC_EYE = {SPRITE_ARC_EYE_ROWS, 5};

const char* const SPRITE_W_MOUTH_ROWS[] = {
  "##         ##",
  " ##       ## ",
  "  ##  #  ##  ",
  "   ### ###   ",
  "    ## ##    ",
};
const PixelSprite SPRITE_W_MOUTH = {SPRITE_W_MOUTH_ROWS, 5};

const char* const SPRITE_TRIANGLE_MOUTH_ROWS[] = {
  "#############",
  " ########### ",
  "  #########  ",
  "   #######   ",
  "    #####    ",
  "     ###     ",
  "      #      ",
};
const PixelSprite SPRITE_TRIANGLE_MOUTH = {SPRITE_TRIANGLE_MOUTH_ROWS, 7};

const char* const SPRITE_SEGMENTED_GRIN_ROWS[] = {
  " ######################### ",
  "###########################",
  "###########################",
  " ######################### ",
  "  #######################  ",
  "   #####################   ",
  "    ###################    ",
};
const PixelSprite SPRITE_SEGMENTED_GRIN = {SPRITE_SEGMENTED_GRIN_ROWS, 7};

const char* const SPRITE_HEART_ROWS[] = {
  "  ###   ###  ",
  " ##### ##### ",
  "#############",
  "#############",
  " ########### ",
  "  #########  ",
  "   #######   ",
  "    #####    ",
  "     ###     ",
  "      #      ",
};
const PixelSprite SPRITE_HEART = {SPRITE_HEART_ROWS, 10};

const char* const SPRITE_PILL_MOUTH_ROWS[] = {
  "  #########  ",
  " ########### ",
  "#############",
  " ########### ",
  "  #########  ",
};
const PixelSprite SPRITE_PILL_MOUTH = {SPRITE_PILL_MOUTH_ROWS, 5};

const char* const SPRITE_SMUG_EYE_ROWS[] = {
  "#############",
  "#############",
  "####         ",
  "####         ",
};
const PixelSprite SPRITE_SMUG_EYE = {SPRITE_SMUG_EYE_ROWS, 4};

const char* const SPRITE_RING_EYE_ROWS[] = {
  "  ###  ",
  " #   # ",
  "#     #",
  "#     #",
  "#     #",
  " #   # ",
  "  ###  ",
};
const PixelSprite SPRITE_RING_EYE = {SPRITE_RING_EYE_ROWS, 7};

const char* const SPRITE_TRAPEZOID_MOUTH_ROWS[] = {
  "   #######   ",
  "   #######   ",
  "  #########  ",
  "  #########  ",
  " ########### ",
  " ########### ",
  "#############",
  "#############",
  "#############",
};
const PixelSprite SPRITE_TRAPEZOID_MOUTH = {SPRITE_TRAPEZOID_MOUTH_ROWS, 9};

const char* const SPRITE_CLOSED_EYE_ROWS[] = {
  "#############",
  "  #########  ",
  "    #####    ",
};
const PixelSprite SPRITE_CLOSED_EYE = {SPRITE_CLOSED_EYE_ROWS, 3};

struct EyeSpan {
  int8_t left;
  int8_t right;
};

const EyeSpan BASE_IDLE_EYE_PROFILE[] = {
  {10, 17}, {8, 19}, {6, 21}, {5, 22}, {4, 23}, {3, 24}, {3, 25}, {2, 25},
  {2, 26}, {1, 26}, {1, 27}, {0, 27}, {0, 27}, {0, 27}, {0, 27}, {0, 27},
  {0, 27}, {0, 27}, {0, 27}, {0, 27}, {0, 27}, {0, 26}, {0, 26}, {1, 25},
  {2, 25}, {3, 24}, {4, 24}, {5, 23}, {7, 21}, {9, 19}, {14, 15},
};

const uint8_t* glyphFor(char character) {
  for (const Glyph& glyph : FONT) {
    if (glyph.character == character) {
      return glyph.columns;
    }
  }
  return FONT[0].columns;
}

bool deviceAt(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void sendCommand(uint8_t command) {
  if (!oledAddress) {
    return;
  }
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
  memset(frameBuffer, 0, sizeof(frameBuffer));
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

void fillRect(int x, int y, int width, int height, bool enabled);

void drawPixelSprite(const PixelSprite& sprite, int centerX, int topY, int scale = 2, bool mirrored = false) {
  int width = strlen(sprite.rows[0]);
  int leftX = centerX - width * scale / 2;
  for (int row = 0; row < sprite.height; row++) {
    for (int column = 0; column < width; column++) {
      int sourceColumn = mirrored ? width - column - 1 : column;
      if (sprite.rows[row][sourceColumn] != '#') {
        continue;
      }
      fillRect(leftX + column * scale, topY + row * scale, scale, scale, true);
    }
  }
}

void drawLine(int x0, int y0, int x1, int y1, bool enabled = true) {
  int dx = abs(x1 - x0);
  int sx = x0 < x1 ? 1 : -1;
  int dy = -abs(y1 - y0);
  int sy = y0 < y1 ? 1 : -1;
  int error = dx + dy;
  while (true) {
    setPixel(x0, y0, enabled);
    if (x0 == x1 && y0 == y1) {
      break;
    }
    int twiceError = 2 * error;
    if (twiceError >= dy) {
      error += dy;
      x0 += sx;
    }
    if (twiceError <= dx) {
      error += dx;
      y0 += sy;
    }
  }
}

void drawRect(int x, int y, int width, int height, bool enabled = true) {
  drawLine(x, y, x + width - 1, y, enabled);
  drawLine(x, y + height - 1, x + width - 1, y + height - 1, enabled);
  drawLine(x, y, x, y + height - 1, enabled);
  drawLine(x + width - 1, y, x + width - 1, y + height - 1, enabled);
}

void fillRect(int x, int y, int width, int height, bool enabled = true) {
  for (int dx = 0; dx < width; dx++) {
    for (int dy = 0; dy < height; dy++) {
      setPixel(x + dx, y + dy, enabled);
    }
  }
}

void drawBaseIdleEye(int centerX, int topY, bool mirrored = false) {
  const int eyeWidth = 28;
  const int leftX = centerX - eyeWidth / 2;
  const int rows = sizeof(BASE_IDLE_EYE_PROFILE) / sizeof(BASE_IDLE_EYE_PROFILE[0]);
  for (int row = 0; row < rows; row++) {
    int localLeft = BASE_IDLE_EYE_PROFILE[row].left;
    int localRight = BASE_IDLE_EYE_PROFILE[row].right;
    if (mirrored) {
      int mirroredLeft = eyeWidth - 1 - localRight;
      localRight = eyeWidth - 1 - localLeft;
      localLeft = mirroredLeft;
    }
    drawLine(leftX + localLeft, topY + row, leftX + localRight, topY + row);
  }
}

void drawCircle(int centerX, int centerY, int radius, bool enabled = true) {
  int x = radius;
  int y = 0;
  int error = 0;
  while (x >= y) {
    setPixel(centerX + x, centerY + y, enabled);
    setPixel(centerX + y, centerY + x, enabled);
    setPixel(centerX - y, centerY + x, enabled);
    setPixel(centerX - x, centerY + y, enabled);
    setPixel(centerX - x, centerY - y, enabled);
    setPixel(centerX - y, centerY - x, enabled);
    setPixel(centerX + y, centerY - x, enabled);
    setPixel(centerX + x, centerY - y, enabled);
    y++;
    if (error <= 0) {
      error += 2 * y + 1;
    }
    if (error > 0) {
      x--;
      error -= 2 * x + 1;
    }
  }
}

void fillCircle(int centerX, int centerY, int radius, bool enabled = true) {
  for (int y = -radius; y <= radius; y++) {
    int span = sqrt(radius * radius - y * y);
    drawLine(centerX - span, centerY + y, centerX + span, centerY + y, enabled);
  }
}

void drawEllipse(int centerX, int centerY, int radiusX, int radiusY, bool enabled = true) {
  int previousX = centerX + radiusX;
  int previousY = centerY;
  for (int degrees = 6; degrees <= 360; degrees += 6) {
    int x = centerX + cos(degrees * DEG_TO_RAD) * radiusX;
    int y = centerY + sin(degrees * DEG_TO_RAD) * radiusY;
    drawLine(previousX, previousY, x, y, enabled);
    previousX = x;
    previousY = y;
  }
}

void fillEllipse(int centerX, int centerY, int radiusX, int radiusY, bool enabled = true) {
  radiusX = max(1, radiusX);
  radiusY = max(1, radiusY);
  for (int y = -radiusY; y <= radiusY; y++) {
    float ratio = 1.0 - ((float)(y * y) / (float)(radiusY * radiusY));
    int span = round(radiusX * sqrt(max(0.0f, ratio)));
    drawLine(centerX - span, centerY + y, centerX + span, centerY + y, enabled);
  }
}

void drawArc(int centerX, int centerY, int radius, int startDegrees, int endDegrees) {
  int previousX = centerX + cos(startDegrees * DEG_TO_RAD) * radius;
  int previousY = centerY + sin(startDegrees * DEG_TO_RAD) * radius;
  for (int degrees = startDegrees + 6; degrees <= endDegrees; degrees += 6) {
    int x = centerX + cos(degrees * DEG_TO_RAD) * radius;
    int y = centerY + sin(degrees * DEG_TO_RAD) * radius;
    drawLine(previousX, previousY, x, y);
    previousX = x;
    previousY = y;
  }
}

void drawQuadratic(int startX, int startY, int controlX, int controlY, int endX, int endY) {
  int previousX = startX;
  int previousY = startY;
  for (int step = 1; step <= 16; step++) {
    float amount = step / 16.0;
    float inverse = 1.0 - amount;
    int x = round(inverse * inverse * startX + 2 * inverse * amount * controlX + amount * amount * endX);
    int y = round(inverse * inverse * startY + 2 * inverse * amount * controlY + amount * amount * endY);
    drawLine(previousX, previousY, x, y);
    previousX = x;
    previousY = y;
  }
}

void drawChar(int x, int y, char character) {
  const uint8_t* columns = glyphFor(character);
  for (int column = 0; column < 5; column++) {
    for (int row = 0; row < 7; row++) {
      if (columns[column] & (1 << row)) {
        setPixel(x + column, y + row);
      }
    }
  }
}

void drawText(int x, int y, const char* text) {
  while (*text) {
    drawChar(x, y, *text);
    x += 6;
    text++;
  }
}

void sendFrame() {
  if (!oledAddress) {
    return;
  }
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

bool drawGeneratedExpressionBitmap(const String& expression, unsigned long now) {
  for (size_t index = 0; index < NIWA_OLED_BITMAP_COUNT; index++) {
    const NiwaOledBitmapExpression& item = NIWA_OLED_BITMAPS[index];
    if (expression != item.id) {
      continue;
    }

    uint8_t frameIndex = 0;
    if (item.frame_count > 1) {
      frameIndex = (now / 520) % item.frame_count;
    }
    const uint8_t* bitmap = item.frames[frameIndex];
    for (size_t offset = 0; offset < OLED_BUFFER_SIZE; offset++) {
      frameBuffer[offset] = pgm_read_byte(bitmap + offset);
    }
    return true;
  }
  return false;
}

void drawEye(int x, int y, int width, int height, int pupilX = 0, int pupilY = 0, bool pupil = false) {
  int radiusX = max(2, width / 2);
  int radiusY = max(1, height / 2);
  fillEllipse(x, y, radiusX, radiusY);
  if (pupil && radiusY > 3) {
    fillCircle(x + pupilX, y + pupilY, min(4, radiusY / 2), false);
  }
}

void drawHeart(int x, int y, int size) {
  fillCircle(x - size / 3, y - size / 4, size / 3);
  fillCircle(x + size / 3, y - size / 4, size / 3);
  for (int row = 0; row <= size; row++) {
    int span = size - row;
    drawLine(x - span, y + row / 2, x + span, y + row / 2);
  }
}

void drawSmileMouth(int x, int y, int width = 20, int depth = 5) {
  drawQuadratic(x - width / 2, y, x, y + depth, x + width / 2, y);
}

void drawFrownMouth(int x, int y, int width = 20, int depth = 5) {
  drawQuadratic(x - width / 2, y, x, y - depth, x + width / 2, y);
}

void drawWMouth(int x, int y, int width = 20, int depth = 5) {
  drawQuadratic(x - width / 2, y, x - width / 4, y + depth, x, y);
  drawQuadratic(x, y, x + width / 4, y + depth, x + width / 2, y);
}

void drawBrow(int x, int y, int tilt, int width = 22) {
  drawLine(x - width / 2, y - tilt, x + width / 2, y + tilt);
}

void drawSparkle(int x, int y, int size = 4) {
  drawLine(x - size, y, x + size, y);
  drawLine(x, y - size, x, y + size);
}

void drawDomeEye(int x, int y, int radiusX = 14, int radiusY = 9) {
  fillEllipse(x, y, radiusX, radiusY);
  fillRect(x - radiusX - 1, y + 3, radiusX * 2 + 3, radiusY + 2, false);
  drawQuadratic(x - radiusX, y + 2, x, y + 5, x + radiusX, y + 2);
}

void drawSqueezedEye(int x, int y, int direction, int width = 20, int height = 10) {
  int tipX = x + direction * width / 2;
  int tailX = x - direction * width / 2;
  drawLine(tailX, y - height / 2, tipX, y);
  drawLine(tipX, y, tailX, y + height / 2);
}

void fillTriangleMouth(int x, int y, int width = 16, int height = 14) {
  int topY = y - height / 2;
  for (int row = 0; row <= height; row++) {
    int span = round((width / 2.0) * (1.0 - (float)row / height));
    drawLine(x - span, topY + row, x + span, topY + row);
  }
}

void fillTrapezoidMouth(int x, int y, int topWidth = 12, int bottomWidth = 18, int height = 16) {
  int topY = y - height / 2;
  for (int row = 0; row <= height; row++) {
    int width = topWidth + (bottomWidth - topWidth) * row / height;
    drawLine(x - width / 2, topY + row, x + width / 2, topY + row);
  }
}

void drawSegmentedGrin(int x, int y, int width = 42, int height = 13, int segments = 6) {
  fillEllipse(x, y, width / 2, height / 2);
  fillRect(x - width / 2 - 1, y - height / 2 - 1, width + 2, height / 2, false);
  drawQuadratic(x - width / 2, y - 1, x, y + height / 2 + 2, x + width / 2, y - 1);
  for (int segment = 1; segment < segments; segment++) {
    int separatorX = x - width / 2 + width * segment / segments;
    drawLine(separatorX, y - 1, separatorX, y + height / 2 + 1, false);
  }
}

void drawTear(int x, int y) {
  drawLine(x, y - 4, x - 3, y + 2);
  drawLine(x - 3, y + 2, x, y + 5);
  drawLine(x, y + 5, x + 3, y + 2);
  drawLine(x + 3, y + 2, x, y - 4);
}

void drawSobbingTearColumn(int centerX, int topY, int height, int phaseOffset = 0) {
  unsigned long now = millis();
  for (int row = 0; row < height; row++) {
    int attach = row < 8 ? row : 8;
    float flow = (row + phaseOffset) * 0.30f - (now % 1600) / 85.0f;
    int wave = row < 4 ? 0 : round((sin(flow) * 3.0f + sin(flow * 0.56f + 1.2f) * 1.5f) * attach / 8.0f);
    int width = 7 + min(row, 14) / 2;
    if (row > height - 9) {
      width -= (row - (height - 9)) / 2;
    }
    width = max(7, min(width, 15));
    int x = centerX + wave;
    drawLine(x - width / 2, topY + row, x + width / 2, topY + row);
  }
}

void drawSobbingMouth(int x, int y) {
  for (int row = -7; row <= 8; row++) {
    int halfWidth = 29 - abs(row);
    if (row > -2 && row < 5) {
      halfWidth += 5;
    }
    drawLine(x - halfWidth, y + row, x + halfWidth, y + row);
  }
}

void drawStress(int x, int y) {
  drawLine(x, y, x + 5, y - 5);
  drawLine(x + 3, y + 4, x + 9, y);
  drawLine(x + 7, y + 7, x + 12, y + 4);
}

void drawReferenceBlink(int yOffset = 0) {
  drawPixelSprite(SPRITE_CLOSED_EYE, 36, 25 + yOffset);
  drawPixelSprite(SPRITE_CLOSED_EYE, 92, 25 + yOffset);
}

bool drawReferenceFace(const String& expression, int yOffset = 0) {
  if (expression == "idle") {
    drawBaseIdleEye(36, 14 + yOffset);
    drawBaseIdleEye(92, 14 + yOffset, true);
  } else if (expression == "serene") {
    drawPixelSprite(SPRITE_DOME_EYE, 36, 17 + yOffset);
    drawPixelSprite(SPRITE_DOME_EYE, 92, 17 + yOffset);
  } else if (expression == "happy") {
    drawPixelSprite(SPRITE_DOME_EYE, 36, 11 + yOffset);
    drawPixelSprite(SPRITE_DOME_EYE, 92, 11 + yOffset);
    drawPixelSprite(SPRITE_W_MOUTH, 64, 42 + yOffset);
  } else if (expression == "wink") {
    drawPixelSprite(SPRITE_DOME_EYE, 36, 13 + yOffset);
    drawPixelSprite(SPRITE_CHEVRON, 92, 12 + yOffset, 2, true);
    drawPixelSprite(SPRITE_W_MOUTH, 64, 43 + yOffset);
  } else if (expression == "joyful") {
    drawPixelSprite(SPRITE_CHEVRON, 36, 11 + yOffset);
    drawPixelSprite(SPRITE_CHEVRON, 92, 11 + yOffset, 2, true);
    drawPixelSprite(SPRITE_TRIANGLE_MOUTH, 64, 40 + yOffset);
  } else if (expression == "laughing") {
    drawPixelSprite(SPRITE_CHEVRON, 36, 7 + yOffset);
    drawPixelSprite(SPRITE_CHEVRON, 92, 7 + yOffset, 2, true);
    drawPixelSprite(SPRITE_SEGMENTED_GRIN, 64, 35 + yOffset);
    for (int separator = 1; separator < 7; separator++) {
      int separatorX = 64 - 27 + (54 * separator / 7);
      drawLine(separatorX, 38 + yOffset, separatorX, 48 + yOffset, false);
    }
  } else if (expression == "cheerful") {
    drawPixelSprite(SPRITE_ARC_EYE, 36, 14 + yOffset);
    drawPixelSprite(SPRITE_ARC_EYE, 92, 14 + yOffset);
    drawPixelSprite(SPRITE_TRIANGLE_MOUTH, 64, 39 + yOffset);
  } else if (expression == "love") {
    drawPixelSprite(SPRITE_HEART, 36, 7 + yOffset);
    drawPixelSprite(SPRITE_HEART, 92, 7 + yOffset);
    drawPixelSprite(SPRITE_PILL_MOUTH, 64, 43 + yOffset);
  } else if (expression == "sobbing") {
    int shake = round(sin(millis() / 1000.0f * 11.5f));
    drawSobbingTearColumn(25, 25 + yOffset + shake, 38, 0);
    drawSobbingTearColumn(103, 25 + yOffset + shake, 38, 21);
    drawSobbingMouth(64, 49 + yOffset);
    drawPixelSprite(SPRITE_CHEVRON, 36, 8 + yOffset + shake);
    drawPixelSprite(SPRITE_CHEVRON, 92, 8 + yOffset + shake, 2, true);
  } else if (expression == "smug") {
    drawPixelSprite(SPRITE_SMUG_EYE, 36, 18 + yOffset);
    drawPixelSprite(SPRITE_SMUG_EYE, 92, 18 + yOffset, 2, true);
    drawPixelSprite(SPRITE_W_MOUTH, 64, 39 + yOffset);
  } else if (expression == "shocked") {
    drawPixelSprite(SPRITE_RING_EYE, 36, 14 + yOffset);
    drawPixelSprite(SPRITE_RING_EYE, 92, 14 + yOffset);
    drawPixelSprite(SPRITE_TRAPEZOID_MOUTH, 64, 38 + yOffset);
  } else if (expression == "surprised") {
    drawPixelSprite(SPRITE_ROUND_EYE, 36, 8 + yOffset);
    drawPixelSprite(SPRITE_ROUND_EYE, 92, 8 + yOffset);
    fillCircle(64, 52 + yOffset, 4);
  } else {
    return false;
  }
  return true;
}

void drawWifiMark() {
  if (WiFi.status() == WL_CONNECTED) {
    setPixel(123, 4);
    drawArc(123, 7, 4, 205, 335);
    drawArc(123, 7, 7, 205, 335);
  } else {
    drawLine(118, 2, 126, 10);
    drawLine(126, 2, 118, 10);
  }
}

void drawDiagnosticScreen(unsigned long now) {
  drawText(4, 3, "NIWA");
  drawText(4, 15, WiFi.status() == WL_CONNECTED ? "WIFI OK" : wifiStateLabel.c_str());
  if (WiFi.status() == WL_CONNECTED) {
    drawText(4, 27, serverStateLabel.c_str());
  } else if (wifiConfigSource.startsWith("local")) {
    drawText(4, 27, "SRC LOCAL");
  } else if (wifiConfigSource == "esp32 memory") {
    drawText(4, 27, "SRC ESP");
  } else {
    drawText(4, 27, "SRC NONE");
  }

  char detailLine[22];
  if (WiFi.status() == WL_CONNECTED) {
    snprintf(detailLine, sizeof(detailLine), "RSSI %d", WiFi.RSSI());
  } else if (lastWifiChannel > 0) {
    snprintf(detailLine, sizeof(detailLine), "CH %d RSSI %d", lastWifiChannel, lastWifiRssi);
  } else if (lastWifiReason) {
    snprintf(detailLine, sizeof(detailLine), "ERR %d", lastWifiReason);
  } else {
    snprintf(detailLine, sizeof(detailLine), "FW 0.3.11");
  }
  drawText(4, 39, detailLine);

  int pulse = (now / 280) % 4;
  for (int index = 0; index < pulse; index++) {
    fillCircle(104 + index * 8, 54, 2);
  }
}

void renderExpression(unsigned long now) {
  clearFrame();
  float seconds = now / 1000.0;
  int bounce = round(sin(seconds * 2.4) * 2);
  int leftX = 36;
  int rightX = 92;
  int eyeY = 26 + bounce;
  int mouthY = 50 + bounce;
  float naturalBlink = (now % 4300 > 4200) ? 0.08 : 1.0;
  int eyeHeight = max(2, (int)(24 * eyeOpenAmount * naturalBlink));
  int lookX = round(sin(seconds * 0.7) * 3);
  int lookY = round(cos(seconds * 0.53));

  if (WiFi.status() != WL_CONNECTED || !serverOnline) {
    drawDiagnosticScreen(now);
    sendFrame();
    return;
  }

  if (transitionPhase == 1 || naturalBlink < 0.5) {
    if (!drawGeneratedExpressionBitmap("blink", now)) {
      drawReferenceBlink();
    }
    sendFrame();
    return;
  }

  if (drawGeneratedExpressionBitmap(activeExpression, now)) {
    if (activeExpression == "photo_capture" && now % 240 < 100) {
      memset(frameBuffer, 0xFF, sizeof(frameBuffer));
    }
    sendFrame();
    return;
  }

  if (drawReferenceFace(activeExpression, activeExpression == "laughing" ? bounce : 0)) {
    sendFrame();
    return;
  }

  if (activeExpression == "serene") {
    drawDomeEye(leftX, eyeY);
    drawDomeEye(rightX, eyeY);
  } else if (activeExpression == "happy") {
    drawDomeEye(leftX, eyeY);
    drawDomeEye(rightX, eyeY);
    drawWMouth(64, mouthY, 20, 5);
  } else if (activeExpression == "joyful") {
    drawSqueezedEye(leftX, eyeY, -1, 22, 11);
    drawSqueezedEye(rightX, eyeY, 1, 22, 11);
    fillTriangleMouth(64, mouthY, 18, 15);
  } else if (activeExpression == "laughing") {
    int jump = round(sin(seconds * 7) * 2);
    drawSqueezedEye(leftX, eyeY + jump, -1, 24, 12);
    drawSqueezedEye(rightX, eyeY + jump, 1, 24, 12);
    drawSegmentedGrin(64, mouthY, 46, 14, 7);
  } else if (activeExpression == "cheerful") {
    drawQuadratic(leftX - 15, eyeY + 2, leftX, eyeY - 10, leftX + 15, eyeY + 2);
    drawQuadratic(rightX - 15, eyeY + 2, rightX, eyeY - 10, rightX + 15, eyeY + 2);
    fillTriangleMouth(64, mouthY, 18, 15);
  } else if (activeExpression == "curious") {
    drawEye(leftX, eyeY, 31, max(2, (int)(27 * eyeOpenAmount)));
    drawEye(rightX, eyeY + 3, 21, max(2, (int)(17 * eyeOpenAmount)));
    drawBrow(leftX, eyeY - 19, -3, 22);
    drawBrow(rightX, eyeY - 13, 3, 16);
    drawEllipse(64, mouthY, 4, 5);
    drawText(112, 8, "?");
  } else if (activeExpression == "excited") {
    drawEye(leftX, eyeY, 33, max(2, (int)(27 * eyeOpenAmount * naturalBlink)), 0, 1);
    drawEye(rightX, eyeY, 33, max(2, (int)(27 * eyeOpenAmount * naturalBlink)), 0, 1);
    fillEllipse(64, mouthY, 9, 6);
    drawSparkle(10, 10, 4);
    drawSparkle(116, 10, 4);
  } else if (activeExpression == "sleepy") {
    drawEye(leftX, eyeY, 31, max(2, (int)(9 * eyeOpenAmount)), 0, 1);
    drawEye(rightX, eyeY, 31, max(2, (int)(9 * eyeOpenAmount)), 0, 1);
    drawLine(56, mouthY, 72, mouthY);
  } else if (activeExpression == "sleeping" || activeExpression == "fall_asleep") {
    drawQuadratic(leftX - 14, eyeY, leftX, eyeY + 4, leftX + 14, eyeY);
    drawQuadratic(rightX - 14, eyeY, rightX, eyeY + 4, rightX + 14, eyeY);
    drawText(105, 13, "Z");
    drawText(113, 4, "Z");
  } else if (activeExpression == "alert") {
    drawEye(leftX, eyeY, 33, max(2, (int)(29 * eyeOpenAmount)), 0, 0);
    drawEye(rightX, eyeY, 33, max(2, (int)(29 * eyeOpenAmount)), 0, 0);
    drawBrow(leftX, eyeY - 19, 0, 22);
    drawBrow(rightX, eyeY - 19, 0, 22);
    drawEllipse(64, mouthY, 3, 4);
  } else if (activeExpression == "surprised") {
    drawEye(leftX, eyeY, 33, max(2, (int)(33 * eyeOpenAmount)));
    drawEye(rightX, eyeY, 33, max(2, (int)(33 * eyeOpenAmount)));
    fillCircle(64, mouthY, 3);
    drawText(112, 8, "!");
  } else if (activeExpression == "shocked") {
    drawCircle(leftX, eyeY, 4);
    drawCircle(rightX, eyeY, 4);
    fillTrapezoidMouth(64, mouthY, 11, 19, 17);
  } else if (activeExpression == "confused") {
    drawEye(leftX, eyeY + 2, 29, max(2, (int)(17 * eyeOpenAmount)));
    drawEye(rightX, eyeY - 1, 25, max(2, (int)(23 * eyeOpenAmount)));
    drawBrow(leftX, eyeY - 16, 3, 22);
    drawBrow(rightX, eyeY - 18, -4, 20);
    drawLine(55, mouthY + 2, 73, mouthY - 2);
    drawText(112, 8, "?");
  } else if (activeExpression == "smug") {
    drawEye(leftX, eyeY, 31, max(2, (int)(10 * eyeOpenAmount)));
    drawEye(rightX, eyeY, 31, max(2, (int)(10 * eyeOpenAmount)));
    drawWMouth(64, mouthY, 20, 4);
  } else if (activeExpression == "sad") {
    drawBrow(leftX, eyeY - 16, -4, 22);
    drawBrow(rightX, eyeY - 16, 4, 22);
    drawEye(leftX, eyeY + 3, 29, max(2, (int)(17 * eyeOpenAmount)));
    drawEye(rightX, eyeY + 3, 29, max(2, (int)(17 * eyeOpenAmount)));
    drawFrownMouth(64, mouthY + 4, 20, 5);
    drawTear(111, 43);
  } else if (activeExpression == "annoyed") {
    drawBrow(leftX, eyeY - 13, 5, 26);
    drawBrow(rightX, eyeY - 13, -5, 26);
    drawEye(leftX, eyeY + 3, 31, max(2, (int)(9 * eyeOpenAmount)));
    drawEye(rightX, eyeY + 3, 31, max(2, (int)(9 * eyeOpenAmount)));
    drawLine(55, mouthY + 2, 73, mouthY + 2);
    drawStress(109, 10);
  } else if (activeExpression == "love") {
    int pulse = (now % 900 < 450) ? 11 : 13;
    drawHeart(leftX, eyeY - 4, pulse);
    drawHeart(rightX, eyeY - 4, pulse);
    drawSmileMouth(64, mouthY, 18, 4);
  } else if (activeExpression == "thinking") {
    drawEye(leftX + 4, eyeY - 3, 31, eyeHeight);
    drawEye(rightX + 4, eyeY - 3, 31, eyeHeight);
    fillCircle(106, 19, 2);
    fillCircle(114, 13, 3);
    fillCircle(123, 6, 4);
    drawLine(59, mouthY + 2, 69, mouthY - 1);
  } else if (activeExpression == "photo_mode" || activeExpression == "photo_capture") {
    drawRect(leftX - 17, eyeY - 17, 34, 34);
    drawRect(rightX - 17, eyeY - 17, 34, 34);
    drawLine(leftX - 8, eyeY, leftX + 8, eyeY);
    drawLine(leftX, eyeY - 8, leftX, eyeY + 8);
    drawLine(rightX - 8, eyeY, rightX + 8, eyeY);
    drawLine(rightX, eyeY - 8, rightX, eyeY + 8);
    if (activeExpression == "photo_capture" && now % 240 < 100) {
      memset(frameBuffer, 0xFF, sizeof(frameBuffer));
    }
  } else if (activeExpression == "tracking") {
    int pupilX = round(sin(seconds * 2.0) * 7);
    int pupilY = round(cos(seconds * 1.6) * 4);
    drawEye(leftX, eyeY, 31, eyeHeight, pupilX, pupilY, true);
    drawEye(rightX, eyeY, 31, eyeHeight, pupilX, pupilY, true);
  } else if (activeExpression == "scanning") {
    drawEye(leftX, eyeY, 31, eyeHeight, 0, 0, false);
    drawEye(rightX, eyeY, 31, eyeHeight, 0, 0, false);
    int scanY = (now / 18) % OLED_HEIGHT;
    drawLine(0, scanY, OLED_WIDTH - 1, scanY);
  } else if (activeExpression == "offline") {
    drawLine(leftX - 13, eyeY - 13, leftX + 13, eyeY + 13);
    drawLine(leftX + 13, eyeY - 13, leftX - 13, eyeY + 13);
    drawLine(rightX - 13, eyeY - 13, rightX + 13, eyeY + 13);
    drawLine(rightX + 13, eyeY - 13, rightX - 13, eyeY + 13);
    drawLine(55, mouthY + 2, 73, mouthY + 2);
  } else if (activeExpression == "wink") {
    drawDomeEye(leftX, eyeY);
    drawSqueezedEye(rightX, eyeY, 1, 20, 10);
    drawWMouth(64, mouthY, 18, 4);
  } else if (activeExpression == "blink") {
    drawQuadratic(leftX - 14, eyeY, leftX, eyeY + 3, leftX + 14, eyeY);
    drawQuadratic(rightX - 14, eyeY, rightX, eyeY + 3, rightX + 14, eyeY);
  } else if (activeExpression == "wake_up") {
    int wakingHeight = max(2, (int)(24 * ((now % 1800) / 1800.0)));
    drawEye(leftX, eyeY, 31, wakingHeight);
    drawEye(rightX, eyeY, 31, wakingHeight);
  } else {
    drawEye(leftX + lookX, eyeY + lookY, 31, eyeHeight);
    drawEye(rightX + lookX, eyeY + lookY, 31, eyeHeight);
    drawSmileMouth(64, mouthY, 14, 3);
  }
  sendFrame();
}

void setTargetExpression(const String& expression) {
  if (!expression.length() || expression == targetExpression) {
    return;
  }
  targetExpression = expression;
  transitionPhase = 1;
  Serial.print("Nuova espressione: ");
  Serial.println(expression);
}

void updateTransition() {
  if (transitionPhase == 1) {
    eyeOpenAmount -= 0.18;
    if (eyeOpenAmount <= 0.05) {
      eyeOpenAmount = 0.05;
      activeExpression = targetExpression;
      transitionPhase = 2;
    }
  } else if (transitionPhase == 2) {
    eyeOpenAmount += 0.18;
    if (eyeOpenAmount >= 1.0) {
      eyeOpenAmount = 1.0;
      transitionPhase = 0;
    }
  }
}

String jsonString(const String& value) {
  String escaped = value;
  escaped.replace("\\", "\\\\");
  escaped.replace("\"", "\\\"");
  return "\"" + escaped + "\"";
}

String extractJsonString(const String& json, const String& key) {
  String marker = "\"" + key + "\":";
  int start = json.indexOf(marker);
  if (start < 0) {
    return "";
  }
  start = json.indexOf('"', start + marker.length());
  if (start < 0) {
    return "";
  }
  int end = json.indexOf('"', start + 1);
  if (end < 0) {
    return "";
  }
  return json.substring(start + 1, end);
}

int extractJsonInt(const String& json, const String& key, int fallback) {
  String marker = "\"" + key + "\":";
  int start = json.indexOf(marker);
  if (start < 0) {
    return fallback;
  }
  start += marker.length();
  while (start < json.length() && json[start] == ' ') {
    start++;
  }
  return json.substring(start).toInt();
}

String boolJson(bool value) {
  return value ? "true" : "false";
}

String statusFromBool(bool value) {
  return value ? "online" : "not-found";
}

String safeCaptureFilename(const String& commandId) {
  String base = commandId.length() ? commandId : String(millis());
  String clean = "";
  for (int index = 0; index < base.length(); index++) {
    char character = base[index];
    if (isalnum(character) || character == '_' || character == '-') {
      clean += character;
    }
  }
  if (!clean.length()) {
    clean = String(millis());
  }
  return "niwa_" + clean + ".jpg";
}

void restoreOledBus() {
  if (!oledAddress) {
    return;
  }
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  initializeDisplay();
}

void initializeCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = CAMERA_Y2_PIN;
  config.pin_d1 = CAMERA_Y3_PIN;
  config.pin_d2 = CAMERA_Y4_PIN;
  config.pin_d3 = CAMERA_Y5_PIN;
  config.pin_d4 = CAMERA_Y6_PIN;
  config.pin_d5 = CAMERA_Y7_PIN;
  config.pin_d6 = CAMERA_Y8_PIN;
  config.pin_d7 = CAMERA_Y9_PIN;
  config.pin_xclk = CAMERA_XCLK_PIN;
  config.pin_pclk = CAMERA_PCLK_PIN;
  config.pin_vsync = CAMERA_VSYNC_PIN;
  config.pin_href = CAMERA_HREF_PIN;
  config.pin_sccb_sda = CAMERA_SIOD_PIN;
  config.pin_sccb_scl = CAMERA_SIOC_PIN;
  config.pin_pwdn = CAMERA_PWDN_PIN;
  config.pin_reset = CAMERA_RESET_PIN;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 14;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t error = esp_camera_init(&config);
  if (error != ESP_OK) {
    cameraOnline = false;
    cameraStateLabel = "not-found";
    Serial.print("Camera non disponibile. esp_camera_init=0x");
    Serial.println(error, HEX);
    return;
  }

  cameraOnline = true;
  cameraStateLabel = "online";
  sensor_t* sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_framesize(sensor, psramFound() ? FRAMESIZE_SVGA : FRAMESIZE_VGA);
    sensor->set_quality(sensor, psramFound() ? 12 : 14);
  }
  Serial.println("Camera ESP32-CAM online.");
}

bool initializeStorage(bool verbose = true) {
  if (sdOnline) {
    return true;
  }

  if (!SD_MMC.begin("/sdcard", true)) {
    sdOnline = false;
    sdStateLabel = "not-found";
    if (verbose) {
      Serial.println("microSD ESP non disponibile.");
    }
    restoreOledBus();
    return false;
  }

  uint8_t cardType = SD_MMC.cardType();
  if (cardType == CARD_NONE) {
    sdOnline = false;
    sdStateLabel = "not-found";
    if (verbose) {
      Serial.println("microSD ESP non rilevata.");
    }
    restoreOledBus();
    return false;
  }

  sdOnline = true;
  sdStateLabel = "online";
  if (verbose) {
    Serial.println("microSD ESP online.");
  }
  restoreOledBus();
  return true;
}

bool saveCaptureToSd(const String& filename, const uint8_t* data, size_t length) {
  if (!initializeStorage(false)) {
    return false;
  }

  SD_MMC.mkdir("/niwa");
  String path = "/niwa/" + filename;
  File file = SD_MMC.open(path, FILE_WRITE);
  if (!file) {
    sdStateLabel = "write-error";
    restoreOledBus();
    return false;
  }
  size_t written = file.write(data, length);
  file.close();
  restoreOledBus();
  if (written != length) {
    sdStateLabel = "write-error";
    return false;
  }
  sdStateLabel = "online";
  return true;
}

bool uploadCapture(const String& commandId, const String& filename, const uint8_t* data, size_t length) {
  if (WiFi.status() != WL_CONNECTED || !serverUrl.length()) {
    return false;
  }

  HTTPClient http;
  http.setConnectTimeout(2500);
  http.setTimeout(6500);
  String url = serverUrl + "/api/devices/" + DEVICE_ID + "/upload-image";
  if (!http.begin(url)) {
    return false;
  }
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-NIWA-Command-ID", commandId);
  http.addHeader("X-NIWA-Filename", filename);
  int statusCode = http.POST((uint8_t*)data, length);
  bool ok = statusCode >= 200 && statusCode < 300;
  markServerStatus(statusCode > 0, statusCode);
  http.end();
  return ok;
}

void reportCommandResult(
  const String& commandId,
  bool ok,
  bool sdSaved,
  bool uploadOk,
  const String& filename,
  const String& message
) {
  if (WiFi.status() != WL_CONNECTED || !serverUrl.length()) {
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(1800);
  http.setTimeout(2600);
  String url = serverUrl + "/api/devices/" + DEVICE_ID + "/command-result";
  if (!http.begin(url)) {
    return;
  }
  http.addHeader("Content-Type", "application/json");
  String payload = "{";
  payload += "\"command_id\":" + jsonString(commandId) + ",";
  payload += "\"ok\":" + boolJson(ok) + ",";
  payload += "\"sd_saved\":" + boolJson(sdSaved) + ",";
  payload += "\"upload_ok\":" + boolJson(uploadOk) + ",";
  payload += "\"filename\":" + jsonString(filename) + ",";
  payload += "\"message\":" + jsonString(message);
  payload += "}";
  int statusCode = http.POST(payload);
  markServerStatus(statusCode > 0, statusCode);
  http.end();
}

void handleCaptureCommand(const String& commandId) {
  if (captureBusy || !commandId.length() || commandId == lastHandledCommandId) {
    return;
  }

  captureBusy = true;
  lastHandledCommandId = commandId;
  setTargetExpression("photo_capture");
  updateTransition();
  renderExpression(millis());

  if (!cameraOnline) {
    initializeCamera();
  }

  if (!cameraOnline) {
    lastCaptureStatus = "camera not-found";
    reportCommandResult(commandId, false, false, false, "", "Camera non disponibile.");
    captureBusy = false;
    return;
  }

  camera_fb_t* frame = esp_camera_fb_get();
  if (!frame) {
    lastCaptureStatus = "capture failed";
    reportCommandResult(commandId, false, false, false, "", "Frame camera non acquisito.");
    captureBusy = false;
    return;
  }

  String filename = safeCaptureFilename(commandId);
  bool sdSaved = saveCaptureToSd(filename, frame->buf, frame->len);
  bool uploadOk = uploadCapture(commandId, filename, frame->buf, frame->len);
  esp_camera_fb_return(frame);

  lastCaptureFilename = filename;
  lastCaptureStatus = uploadOk ? "uploaded" : (sdSaved ? "sd-only" : "failed");
  bool ok = sdSaved || uploadOk;
  String message = ok ? "Scatto gestito." : "Scatto non salvato.";
  reportCommandResult(commandId, ok, sdSaved, uploadOk, filename, message);
  captureBusy = false;
}

bool hasLocalWifiConfig() {
  return LOCAL_WIFI_SSID && LOCAL_WIFI_SSID[0] != '\0';
}

const char* wifiStatusName(wl_status_t status) {
  switch (status) {
    case WL_IDLE_STATUS:
      return "IDLE";
    case WL_NO_SSID_AVAIL:
      return "NO SSID";
    case WL_SCAN_COMPLETED:
      return "SCAN OK";
    case WL_CONNECTED:
      return "CONNECTED";
    case WL_CONNECT_FAILED:
      return "CONNECT FAILED";
    case WL_CONNECTION_LOST:
      return "CONNECTION LOST";
    case WL_DISCONNECTED:
      return "DISCONNECTED";
    default:
      return "UNKNOWN";
  }
}

void applyLocalBuildConfig() {
  bool shouldUseLocalWifi = hasLocalWifiConfig() && (NIWA_COMPANION_USE_LOCAL_WIFI || !wifiSsid.length());
  if (shouldUseLocalWifi) {
    wifiSsid = LOCAL_WIFI_SSID;
    wifiPassword = LOCAL_WIFI_PASSWORD;
    wifiConfigSource = NIWA_COMPANION_USE_LOCAL_WIFI ? "local firmware config" : "local firmware fallback";
  } else if (wifiSsid.length()) {
    wifiConfigSource = "esp32 memory";
  } else {
    wifiConfigSource = "none";
  }

  if (LOCAL_SERVER_URL && LOCAL_SERVER_URL[0] != '\0') {
    if (NIWA_COMPANION_USE_LOCAL_WIFI || !serverUrl.length()) {
      serverUrl = LOCAL_SERVER_URL;
    }
  }
}

void configureWifiRadio() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.setHostname(DEVICE_HOSTNAME);
  wifi_country_t country = {"IT", 1, 13, WIFI_COUNTRY_POLICY_AUTO};
  esp_wifi_set_country(&country);
}

int scanForConfiguredWifi() {
  lastWifiChannel = 0;
  lastWifiRssi = 0;
  if (!wifiSsid.length()) {
    return 0;
  }

  wifiStateLabel = "WIFI SCAN";
  Serial.print("Scansione Wi-Fi per SSID ");
  Serial.println(wifiSsid);
  int count = WiFi.scanNetworks(false, true);
  int bestIndex = -1;
  int bestRssi = -1000;
  for (int index = 0; index < count; index++) {
    if (WiFi.SSID(index) == wifiSsid && WiFi.RSSI(index) > bestRssi) {
      bestIndex = index;
      bestRssi = WiFi.RSSI(index);
    }
  }

  if (bestIndex >= 0) {
    lastWifiChannel = WiFi.channel(bestIndex);
    lastWifiRssi = WiFi.RSSI(bestIndex);
    Serial.print("NIWA-AP trovato. Canale: ");
    Serial.print(lastWifiChannel);
    Serial.print(" RSSI: ");
    Serial.println(lastWifiRssi);
  } else {
    Serial.print("NIWA-AP non trovato nella scansione. Reti viste: ");
    Serial.println(count);
  }
  WiFi.scanDelete();
  return lastWifiChannel;
}

void markServerStatus(bool online, int statusCode = 0) {
  lastHttpStatus = statusCode;
  serverOnline = online;
  if (online) {
    lastServerOkAt = millis();
    serverStateLabel = "SERVER OK";
  } else if (statusCode > 0) {
    serverStateLabel = "SERVER ERR";
  } else {
    serverStateLabel = "SERVER WAIT";
  }
}

void connectWifi(bool forceRestart = false) {
  if (!wifiSsid.length()) {
    wifiStateLabel = "NO WIFI";
    Serial.println("Wi-Fi non configurato. Usa lo script di provisioning NIWA.");
    return;
  }
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (wifiAttemptInProgress && !forceRestart) {
    return;
  }
  if (forceRestart) {
    Serial.println("Timeout Wi-Fi: nuovo tentativo pulito.");
    WiFi.disconnect(false);
    delay(350);
  }
  configureWifiRadio();
  int channel = scanForConfiguredWifi();
  Serial.print("Connessione Wi-Fi a ");
  Serial.println(wifiSsid);
  wifiStateLabel = "WIFI CONN";
  serverOnline = false;
  serverStateLabel = "SERVER WAIT";
  if (channel > 0) {
    WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str(), channel);
  } else {
    WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  }
  lastWifiRetryAt = millis();
  wifiAttemptStartedAt = millis();
  wifiAttemptInProgress = true;
}

void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    wifiAttemptInProgress = false;
    wifiStateLabel = "WIFI OK";
    lastWifiReason = 0;
    lastWifiRssi = WiFi.RSSI();
    lastPollAt = millis() - POLL_INTERVAL_MS;
    lastHeartbeatAt = millis() - HEARTBEAT_INTERVAL_MS;
    Serial.print("Wi-Fi online. IP: ");
    Serial.println(WiFi.localIP());
  } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    wifiAttemptInProgress = false;
    wifi_err_reason_t reason = (wifi_err_reason_t)info.wifi_sta_disconnected.reason;
    lastWifiReason = reason;
    wifiStateLabel = "WIFI DOWN";
    markServerStatus(false);
    Serial.print("Wi-Fi disconnesso. Motivo: ");
    Serial.print(reason);
    Serial.print(" - ");
    Serial.println(WiFi.disconnectReasonName(reason));
  }
}

void printStatus() {
  Serial.println();
  Serial.println("NIWA Companion status");
  Serial.print("Firmware: ");
  Serial.println(FIRMWARE_VERSION);
  Serial.print("OLED: ");
  Serial.println(oledAddress ? "online" : "non trovato");
  Serial.print("Camera: ");
  Serial.println(cameraStateLabel);
  Serial.print("microSD ESP: ");
  Serial.println(sdStateLabel);
  Serial.print("Ultimo scatto: ");
  Serial.println(lastCaptureStatus);
  Serial.print("Wi-Fi SSID: ");
  Serial.println(wifiSsid.length() ? wifiSsid : "(non configurato)");
  Serial.print("Wi-Fi origine: ");
  Serial.println(wifiConfigSource);
  Serial.print("Wi-Fi stato: ");
  Serial.println(WiFi.status() == WL_CONNECTED ? "online" : "offline");
  Serial.print("Wi-Fi dettaglio: ");
  Serial.println(wifiStatusName(WiFi.status()));
  Serial.print("Password length: ");
  Serial.println(wifiPassword.length());
  Serial.print("Local build config: ");
  Serial.println(NIWA_COMPANION_HAS_LOCAL_CONFIG ? "presente" : "assente");
  if (lastWifiChannel > 0) {
    Serial.print("Canale/RSSI ultimi: ");
    Serial.print(lastWifiChannel);
    Serial.print(" / ");
    Serial.println(lastWifiRssi);
  }
  if (lastWifiReason) {
    Serial.print("Ultimo motivo disconnessione: ");
    Serial.println(lastWifiReason);
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  }
  Serial.print("Server: ");
  Serial.println(serverUrl);
  Serial.print("Server stato: ");
  Serial.print(serverStateLabel);
  if (lastHttpStatus) {
    Serial.print(" HTTP ");
    Serial.print(lastHttpStatus);
  }
  Serial.println();
  Serial.print("Espressione: ");
  Serial.println(activeExpression);
}

void handleSerialCommand(String command) {
  command.trim();
  if (!command.length()) {
    return;
  }
  if (command.startsWith("WIFI_SSID=")) {
    wifiSsid = command.substring(10);
    wifiSsid.trim();
    Serial.println("SSID ricevuto.");
  } else if (command.startsWith("WIFI_PASSWORD=")) {
    wifiPassword = command.substring(14);
    Serial.println("Password Wi-Fi ricevuta senza stampa su seriale.");
  } else if (command.startsWith("SERVER_URL=")) {
    serverUrl = command.substring(11);
    serverUrl.trim();
    Serial.println("URL server ricevuto.");
  } else if (command == "SAVE_WIFI") {
    preferences.begin("niwa", false);
    preferences.putString("ssid", wifiSsid);
    preferences.putString("password", wifiPassword);
    preferences.putString("server", serverUrl);
    preferences.end();
    wifiConfigSource = "esp32 memory";
    Serial.println("Configurazione salvata nella memoria ESP32.");
    wifiAttemptInProgress = false;
    WiFi.disconnect(false);
    delay(250);
    connectWifi();
  } else if (command == "CLEAR_WIFI") {
    preferences.begin("niwa", false);
    preferences.clear();
    preferences.end();
    wifiSsid = "";
    wifiPassword = "";
    serverUrl = DEFAULT_SERVER_URL;
    wifiConfigSource = "none";
    applyLocalBuildConfig();
    WiFi.disconnect(true);
    Serial.println("Configurazione Wi-Fi rimossa.");
  } else if (command == "STATUS") {
    printStatus();
  } else if (command == "SCAN_WIFI") {
    configureWifiRadio();
    int count = WiFi.scanNetworks(false, true);
    Serial.print("Reti viste: ");
    Serial.println(count);
    for (int index = 0; index < count; index++) {
      if (WiFi.SSID(index) == wifiSsid) {
        Serial.print("NIWA-AP visto su canale ");
        Serial.print(WiFi.channel(index));
        Serial.print(" RSSI ");
        Serial.print(WiFi.RSSI(index));
        Serial.print(" auth ");
        Serial.println(WiFi.encryptionType(index));
      }
    }
    WiFi.scanDelete();
  } else {
    Serial.println("Comando non riconosciuto.");
  }
}

void readSerialCommands() {
  while (Serial.available()) {
    char character = Serial.read();
    if (character == '\n') {
      handleSerialCommand(serialLine);
      serialLine = "";
    } else if (character != '\r' && serialLine.length() < 220) {
      serialLine += character;
    }
  }
}

void pollExpression() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  HTTPClient http;
  http.setConnectTimeout(1600);
  http.setTimeout(1800);
  String url = serverUrl + "/api/devices/" + DEVICE_ID + "/expression";
  if (!http.begin(url)) {
    return;
  }
  int statusCode = http.GET();
  if (statusCode == HTTP_CODE_OK) {
    markServerStatus(true, statusCode);
    String body = http.getString();
    String expression = extractJsonString(body, "expression");
    int revision = extractJsonInt(body, "revision", remoteRevision);
    if (expression.length() && (revision != remoteRevision || expression != targetExpression)) {
      remoteRevision = revision;
      setTargetExpression(expression);
    }
    String commandType = extractJsonString(body, "command_type");
    String commandId = extractJsonString(body, "command_id");
    if (commandType == "capture_photo" && commandId.length()) {
      handleCaptureCommand(commandId);
    }
  } else {
    markServerStatus(false, statusCode);
  }
  http.end();
}

void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  HTTPClient http;
  http.setConnectTimeout(1600);
  http.setTimeout(1800);
  String url = serverUrl + "/api/devices/" + DEVICE_ID + "/heartbeat";
  if (!http.begin(url)) {
    markServerStatus(false);
    return;
  }
  http.addHeader("Content-Type", "application/json");
  String payload = "{";
  payload += "\"name\":" + jsonString(DEVICE_NAME) + ",";
  payload += "\"ip\":" + jsonString(WiFi.localIP().toString()) + ",";
  payload += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  payload += "\"firmware\":" + jsonString(FIRMWARE_VERSION) + ",";
  payload += "\"oled\":" + jsonString(oledAddress ? "online" : "not-found") + ",";
  payload += "\"camera\":" + jsonString(cameraStateLabel) + ",";
  payload += "\"sd\":" + jsonString(sdStateLabel) + ",";
  payload += "\"last_capture\":" + jsonString(lastCaptureStatus) + ",";
  payload += "\"last_capture_filename\":" + jsonString(lastCaptureFilename) + ",";
  payload += "\"message\":\"Avatar OLED con camera opzionale\"";
  payload += "}";
  int statusCode = http.POST(payload);
  if (statusCode == HTTP_CODE_OK) {
    markServerStatus(true, statusCode);
    String body = http.getString();
    String expression = extractJsonString(body, "expression");
    int revision = extractJsonInt(body, "revision", remoteRevision);
    if (expression.length() && (revision != remoteRevision || expression != targetExpression)) {
      remoteRevision = revision;
      setTargetExpression(expression);
    }
  } else {
    markServerStatus(false, statusCode);
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(750);
  Serial.println();
  Serial.println("NIWA Companion avatar OLED avviato.");

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  if (deviceAt(0x3C)) {
    oledAddress = 0x3C;
  } else if (deviceAt(0x3D)) {
    oledAddress = 0x3D;
  }
  if (oledAddress) {
    initializeDisplay();
    Serial.print("OLED trovato a 0x");
    Serial.println(oledAddress, HEX);
  } else {
    Serial.println("OLED non trovato a 0x3C o 0x3D.");
  }

  initializeCamera();
  initializeStorage();

  preferences.begin("niwa", true);
  wifiSsid = preferences.getString("ssid", "");
  wifiPassword = preferences.getString("password", "");
  serverUrl = preferences.getString("server", DEFAULT_SERVER_URL);
  preferences.end();
  applyLocalBuildConfig();
  WiFi.onEvent(onWifiEvent);
  connectWifi();
  printStatus();
}

void loop() {
  unsigned long now = millis();
  readSerialCommands();

  if (
    WiFi.status() != WL_CONNECTED
    && wifiSsid.length()
    && wifiAttemptInProgress
    && now - wifiAttemptStartedAt >= WIFI_ATTEMPT_TIMEOUT_MS
  ) {
    connectWifi(true);
  } else if (
    WiFi.status() != WL_CONNECTED
    && wifiSsid.length()
    && !wifiAttemptInProgress
    && now - lastWifiRetryAt >= WIFI_RETRY_INTERVAL_MS
  ) {
    connectWifi();
  }
  if (WiFi.status() == WL_CONNECTED && now - lastPollAt >= POLL_INTERVAL_MS) {
    lastPollAt = now;
    pollExpression();
  }
  if (WiFi.status() == WL_CONNECTED && now - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatAt = now;
    sendHeartbeat();
  }
  if (now - lastFrameAt >= FRAME_INTERVAL_MS) {
    lastFrameAt = now;
    updateTransition();
    renderExpression(now);
  }
}
