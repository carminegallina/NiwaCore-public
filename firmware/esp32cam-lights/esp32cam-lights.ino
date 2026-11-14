// Copyright (c) 2026 Carmine Gallina - https://github.com/carminegallina
/*
  NIWA Lights - ESP32-CAM Pan/Tilt firmware v0.5

  Hardware target:
  - ESP32-CAM / AI Thinker ESP32-CAM
  - No camera required
  - Pan servo signal on GPIO 13
  - Tilt servo signal on GPIO 14

  API:
  - GET  /
  - GET  /status
  - POST /move    body: {"pan":90,"tilt":90}
  - POST /center

  Power:
  - Do not power servos from ESP32-CAM.
  - Use external 5V servo power.
  - Connect servo power GND to ESP32-CAM GND.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>

const char* WIFI_SSID = "NIWA-AP";
const char* WIFI_PASSWORD = "INSERISCI_PASSWORD_WIFI";

const char* DEVICE_ID = "light_01";
const char* DEVICE_NAME = "NIWA Light 01";
const char* FIRMWARE_VERSION = "0.5";

const int PAN_PIN = 13;
const int TILT_PIN = 14;

const int PAN_MIN = 0;
const int PAN_MAX = 180;
const int PAN_CENTER = 90;

const int TILT_MIN = 20;
const int TILT_MAX = 160;
const int TILT_CENTER = 90;

const unsigned long WIFI_CHECK_INTERVAL_MS = 5000;
const int WIFI_CONNECT_TIMEOUT_MS = 20000;
const int WIFI_RESTART_AFTER_FAILURES = 12;

Servo panServo;
Servo tiltServo;
WebServer server(80);

int currentPan = PAN_CENTER;
int currentTilt = TILT_CENTER;
unsigned long lastWifiCheck = 0;
int wifiFailureCount = 0;

int clampAngle(int value, int minValue, int maxValue) {
  if (value < minValue) return minValue;
  if (value > maxValue) return maxValue;
  return value;
}

String jsonEscape(const String& value) {
  String result = "";
  for (size_t i = 0; i < value.length(); i++) {
    char c = value[i];
    if (c == '"' || c == '\\') {
      result += '\\';
    }
    result += c;
  }
  return result;
}

int extractJsonInt(const String& body, const String& key, int fallback) {
  String pattern = "\"" + key + "\"";
  int keyIndex = body.indexOf(pattern);
  if (keyIndex < 0) return fallback;

  int colonIndex = body.indexOf(':', keyIndex + pattern.length());
  if (colonIndex < 0) return fallback;

  int start = colonIndex + 1;
  while (start < (int)body.length() && (body[start] == ' ' || body[start] == '\t')) {
    start++;
  }

  int end = start;
  while (end < (int)body.length() && (isDigit(body[end]) || body[end] == '-')) {
    end++;
  }

  if (end <= start) return fallback;
  return body.substring(start, end).toInt();
}

void writeServos(int pan, int tilt) {
  currentPan = clampAngle(pan, PAN_MIN, PAN_MAX);
  currentTilt = clampAngle(tilt, TILT_MIN, TILT_MAX);

  panServo.write(currentPan);
  tiltServo.write(currentTilt);
}

String statusJson(const String& message) {
  String json = "{";
  json += "\"id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"name\":\"" + String(DEVICE_NAME) + "\",";
  json += "\"firmware\":\"" + String(FIRMWARE_VERSION) + "\",";
  json += "\"online\":true,";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"wifi_status\":" + String(WiFi.status()) + ",";
  json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"pan\":" + String(currentPan) + ",";
  json += "\"tilt\":" + String(currentTilt) + ",";
  json += "\"message\":\"" + jsonEscape(message) + "\"";
  json += "}";
  return json;
}

void sendCorsHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void sendJson(int statusCode, const String& body) {
  sendCorsHeaders();
  server.send(statusCode, "application/json", body);
}

void handleOptions() {
  sendCorsHeaders();
  server.send(204);
}

void handleRoot() {
  sendJson(200, statusJson("NIWA Lights ESP32-CAM pronto."));
}

void handleStatus() {
  sendJson(200, statusJson("Modulo online."));
}

void handleMove() {
  String body = server.arg("plain");
  int pan = extractJsonInt(body, "pan", currentPan);
  int tilt = extractJsonInt(body, "tilt", currentTilt);

  writeServos(pan, tilt);

  Serial.print("Move -> pan: ");
  Serial.print(currentPan);
  Serial.print(" tilt: ");
  Serial.println(currentTilt);

  sendJson(200, statusJson("Posizione aggiornata."));
}

void handleCenter() {
  writeServos(PAN_CENTER, TILT_CENTER);
  Serial.println("Center");
  sendJson(200, statusJson("Modulo centrato."));
}

void handleNotFound() {
  sendJson(404, "{\"error\":\"Endpoint non trovato.\"}");
}

void connectWiFi() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.disconnect(true);
  delay(500);

  Serial.println("Scansione reti Wi-Fi...");
  int networkCount = WiFi.scanNetworks();
  if (networkCount <= 0) {
    Serial.println("Nessuna rete trovata.");
  } else {
    for (int i = 0; i < networkCount; i++) {
      Serial.print(" - ");
      Serial.print(WiFi.SSID(i));
      Serial.print(" RSSI ");
      Serial.print(WiFi.RSSI(i));
      Serial.print(" dBm");
      if (WiFi.SSID(i) == WIFI_SSID) {
        Serial.print("  <== target");
      }
      Serial.println();
    }
  }

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connessione a ");
  Serial.print(WIFI_SSID);

  unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.print("Connessione non riuscita. Stato Wi-Fi: ");
    Serial.println(WiFi.status());
    return;
  }

  Serial.print("Connesso. IP: ");
  Serial.println(WiFi.localIP());

  wifiFailureCount = 0;
}

void ensureWiFi() {
  if (millis() - lastWifiCheck < WIFI_CHECK_INTERVAL_MS) {
    return;
  }

  lastWifiCheck = millis();

  if (WiFi.status() == WL_CONNECTED) {
    wifiFailureCount = 0;
    return;
  }

  wifiFailureCount++;
  Serial.print("Wi-Fi non connesso. Stato: ");
  Serial.print(WiFi.status());
  Serial.print(" tentativo: ");
  Serial.println(wifiFailureCount);

  if (wifiFailureCount >= WIFI_RESTART_AFTER_FAILURES) {
    Serial.println("Wi-Fi bloccato troppo a lungo. Riavvio ESP32...");
    delay(500);
    ESP.restart();
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  panServo.setPeriodHertz(50);
  tiltServo.setPeriodHertz(50);
  panServo.attach(PAN_PIN, 500, 2400);
  tiltServo.attach(TILT_PIN, 500, 2400);
  writeServos(PAN_CENTER, TILT_CENTER);

  connectWiFi();

  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/move", HTTP_POST, handleMove);
  server.on("/center", HTTP_POST, handleCenter);

  server.on("/", HTTP_OPTIONS, handleOptions);
  server.on("/status", HTTP_OPTIONS, handleOptions);
  server.on("/move", HTTP_OPTIONS, handleOptions);
  server.on("/center", HTTP_OPTIONS, handleOptions);

  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("NIWA Lights firmware pronto.");
}

void loop() {
  ensureWiFi();
  server.handleClient();
}
