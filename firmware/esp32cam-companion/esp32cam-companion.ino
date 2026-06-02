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
*/

#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <Wire.h>

const char* FIRMWARE_VERSION = "0.1.0";
const char* DEVICE_ID = "companion_01";
const char* DEVICE_NAME = "NIWA Companion 01";
const char* DEFAULT_SERVER_URL = "http://10.42.0.1:5058";

const int I2C_SDA_PIN = 13;
const int I2C_SCL_PIN = 14;
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
int remoteRevision = 0;
int transitionPhase = 0;
float eyeOpenAmount = 1.0;
unsigned long lastFrameAt = 0;
unsigned long lastPollAt = 0;
unsigned long lastHeartbeatAt = 0;
unsigned long lastWifiRetryAt = 0;
unsigned long wifiAttemptStartedAt = 0;
bool wifiAttemptInProgress = false;

struct Glyph {
  char character;
  uint8_t columns[5];
};

const Glyph FONT[] = {
  {' ', {0x00, 0x00, 0x00, 0x00, 0x00}},
  {'-', {0x08, 0x08, 0x08, 0x08, 0x08}},
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
  {'C', {0x3E, 0x41, 0x41, 0x41, 0x22}},
  {'E', {0x7F, 0x49, 0x49, 0x49, 0x41}},
  {'F', {0x7F, 0x09, 0x09, 0x09, 0x01}},
  {'I', {0x00, 0x41, 0x7F, 0x41, 0x00}},
  {'L', {0x7F, 0x40, 0x40, 0x40, 0x40}},
  {'N', {0x7F, 0x02, 0x04, 0x08, 0x7F}},
  {'O', {0x3E, 0x41, 0x41, 0x41, 0x3E}},
  {'P', {0x7F, 0x09, 0x09, 0x09, 0x06}},
  {'R', {0x7F, 0x09, 0x19, 0x29, 0x46}},
  {'S', {0x46, 0x49, 0x49, 0x49, 0x31}},
  {'T', {0x01, 0x01, 0x7F, 0x01, 0x01}},
  {'U', {0x3F, 0x40, 0x40, 0x40, 0x3F}},
  {'W', {0x7F, 0x20, 0x18, 0x20, 0x7F}},
  {'Z', {0x61, 0x51, 0x49, 0x45, 0x43}},
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

void drawEye(int x, int y, int width, int height, int pupilX = 0, int pupilY = 0, bool pupil = true) {
  height = max(2, height);
  fillRect(x - width / 2, y - height / 2, width, height);
  if (pupil && height > 7) {
    fillCircle(x + pupilX, y + pupilY, min(5, height / 4), false);
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

void renderExpression(unsigned long now) {
  clearFrame();
  drawWifiMark();
  float seconds = now / 1000.0;
  int bounce = round(sin(seconds * 2.4) * 2);
  int leftX = 36;
  int rightX = 92;
  int eyeY = 31 + bounce;
  float naturalBlink = (now % 4300 > 4200) ? 0.08 : 1.0;
  int eyeHeight = max(2, (int)(24 * eyeOpenAmount * naturalBlink));

  if (activeExpression == "happy") {
    drawArc(leftX, eyeY + 4, 16, 205, 335);
    drawArc(rightX, eyeY + 4, 16, 205, 335);
  } else if (activeExpression == "curious") {
    drawEye(leftX, eyeY, 29, max(2, (int)(29 * eyeOpenAmount)));
    drawEye(rightX, eyeY + 3, 20, max(2, (int)(18 * eyeOpenAmount)));
  } else if (activeExpression == "excited") {
    drawEye(leftX, eyeY, 31, eyeHeight);
    drawEye(rightX, eyeY, 31, eyeHeight);
    drawLine(8, 9, 15, 16);
    drawLine(15, 9, 8, 16);
    drawLine(112, 9, 119, 16);
    drawLine(119, 9, 112, 16);
  } else if (activeExpression == "sleepy") {
    fillRect(leftX - 15, eyeY, 30, 5);
    fillRect(rightX - 15, eyeY, 30, 5);
  } else if (activeExpression == "sleeping" || activeExpression == "fall_asleep") {
    drawLine(leftX - 15, eyeY, leftX + 15, eyeY + 3);
    drawLine(rightX - 15, eyeY + 3, rightX + 15, eyeY);
    drawText(105, 13, "Z");
    drawText(113, 4, "Z");
  } else if (activeExpression == "alert") {
    drawRect(leftX - 15, eyeY - 16, 30, 32);
    drawRect(rightX - 15, eyeY - 16, 30, 32);
    fillCircle(leftX, eyeY, 4);
    fillCircle(rightX, eyeY, 4);
  } else if (activeExpression == "surprised") {
    drawCircle(leftX, eyeY, 17);
    drawCircle(rightX, eyeY, 17);
    fillCircle(leftX, eyeY, 5);
    fillCircle(rightX, eyeY, 5);
  } else if (activeExpression == "sad") {
    drawLine(leftX - 16, eyeY - 10, leftX + 16, eyeY);
    drawLine(rightX - 16, eyeY, rightX + 16, eyeY - 10);
    fillCircle(leftX, eyeY + 7, 4);
    fillCircle(rightX, eyeY + 7, 4);
  } else if (activeExpression == "annoyed") {
    drawLine(leftX - 16, eyeY - 9, leftX + 16, eyeY);
    drawLine(rightX - 16, eyeY, rightX + 16, eyeY - 9);
    fillRect(leftX - 15, eyeY + 5, 30, 5);
    fillRect(rightX - 15, eyeY + 5, 30, 5);
  } else if (activeExpression == "love") {
    int pulse = (now % 900 < 450) ? 13 : 15;
    drawHeart(leftX, eyeY - 4, pulse);
    drawHeart(rightX, eyeY - 4, pulse);
  } else if (activeExpression == "thinking") {
    drawEye(leftX, eyeY, 31, eyeHeight, 4, -4);
    drawEye(rightX, eyeY, 31, eyeHeight, 4, -4);
    fillCircle(106, 19, 2);
    fillCircle(114, 13, 3);
    fillCircle(123, 6, 4);
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
    drawEye(leftX, eyeY, 31, eyeHeight, pupilX, pupilY);
    drawEye(rightX, eyeY, 31, eyeHeight, pupilX, pupilY);
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
  } else if (activeExpression == "wink") {
    drawEye(leftX, eyeY, 31, eyeHeight);
    drawLine(rightX - 15, eyeY, rightX + 15, eyeY);
  } else if (activeExpression == "blink") {
    drawLine(leftX - 15, eyeY, leftX + 15, eyeY);
    drawLine(rightX - 15, eyeY, rightX + 15, eyeY);
  } else if (activeExpression == "wake_up") {
    int wakingHeight = max(2, (int)(24 * ((now % 1800) / 1800.0)));
    drawEye(leftX, eyeY, 31, wakingHeight);
    drawEye(rightX, eyeY, 31, wakingHeight);
  } else {
    drawEye(leftX, eyeY, 31, eyeHeight);
    drawEye(rightX, eyeY, 31, eyeHeight);
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

void connectWifi(bool forceRestart = false) {
  if (!wifiSsid.length()) {
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
    delay(250);
  }
  Serial.print("Connessione Wi-Fi a ");
  Serial.println(wifiSsid);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  lastWifiRetryAt = millis();
  wifiAttemptStartedAt = millis();
  wifiAttemptInProgress = true;
}

void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    wifiAttemptInProgress = false;
    Serial.print("Wi-Fi online. IP: ");
    Serial.println(WiFi.localIP());
  } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    wifiAttemptInProgress = false;
    wifi_err_reason_t reason = (wifi_err_reason_t)info.wifi_sta_disconnected.reason;
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
  Serial.print("Wi-Fi SSID: ");
  Serial.println(wifiSsid.length() ? wifiSsid : "(non configurato)");
  Serial.print("Wi-Fi stato: ");
  Serial.println(WiFi.status() == WL_CONNECTED ? "online" : "offline");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  }
  Serial.print("Server: ");
  Serial.println(serverUrl);
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
    WiFi.disconnect(true);
    Serial.println("Configurazione Wi-Fi rimossa.");
  } else if (command == "STATUS") {
    printStatus();
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
    String body = http.getString();
    String expression = extractJsonString(body, "expression");
    int revision = extractJsonInt(body, "revision", remoteRevision);
    if (expression.length() && (revision != remoteRevision || expression != targetExpression)) {
      remoteRevision = revision;
      setTargetExpression(expression);
    }
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
    return;
  }
  http.addHeader("Content-Type", "application/json");
  String payload = "{";
  payload += "\"name\":" + jsonString(DEVICE_NAME) + ",";
  payload += "\"ip\":" + jsonString(WiFi.localIP().toString()) + ",";
  payload += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  payload += "\"firmware\":" + jsonString(FIRMWARE_VERSION) + ",";
  payload += "\"oled\":" + jsonString(oledAddress ? "online" : "not-found") + ",";
  payload += "\"message\":\"Avatar OLED connesso\"";
  payload += "}";
  int statusCode = http.POST(payload);
  if (statusCode == HTTP_CODE_OK) {
    String body = http.getString();
    String expression = extractJsonString(body, "expression");
    int revision = extractJsonInt(body, "revision", remoteRevision);
    if (expression.length() && (revision != remoteRevision || expression != targetExpression)) {
      remoteRevision = revision;
      setTargetExpression(expression);
    }
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

  preferences.begin("niwa", true);
  wifiSsid = preferences.getString("ssid", "");
  wifiPassword = preferences.getString("password", "");
  serverUrl = preferences.getString("server", DEFAULT_SERVER_URL);
  preferences.end();
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
