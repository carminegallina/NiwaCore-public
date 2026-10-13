/*
  NIWA Z6 II Wi-Fi Bridge
  ESP32-S3 N16R8 / HW-678

  Nikon Z6 II (PTP/USB Host) -> ESP32-S3 -> NIWA Import on Raspberry Pi.

  Hardware, viewed from the component side with USB ports at the bottom:
    LEFT  USB-C = passive OTG adapter + Nikon data cable
    RIGHT USB-C = PC / COM / Serial Monitor
    Rear USB-OTG solder bridge = CLOSED
    Front IN-OUT bridge       = CLOSED (VBUS path, verified on this board)

  The firmware never deletes or changes camera files. It imports NEF/JPG/JPEG,
  computes the same quick fingerprint used by NIWA Import, asks the Raspberry
  whether the file is already present, and uploads only when requested.

  Serial configuration (115200 baud, "Newline"):
    WIFI_SSID=NIWA-AP
    WIFI_PASSWORD=your_password
    SERVER_URL=http://10.42.0.1:5057/api/bridge/v1
    BRIDGE_TOKEN=your_runtime_token
    SAVE_CONFIG
    STATUS
    RESCAN
    WIFI_SCAN
    WIFI_CONNECT

  The bridge joins Wi-Fi only when it has something to upload, so it stays
  disconnected while no camera is attached. WIFI_CONNECT forces one connection
  attempt, which makes provisioning verifiable on its own.

  Password and token are stored only in ESP32 Preferences/NVS. They are never
  printed and there are no secrets in this source file. STATUS only reports the
  stored password length so a wrong paste can be spotted without exposing it.
*/

#include <Arduino.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <algorithm>
#include <utility>
#include <vector>
#include "esp_arduino_version.h"
#include "esp_err.h"
#include "esp_log.h"
#include "mbedtls/sha256.h"
#include "usb/usb_host.h"

static constexpr char FIRMWARE_VERSION[] = "1.3.0";
static constexpr char DEFAULT_WIFI_SSID[] = "NIWA-AP";
static constexpr char DEFAULT_SERVER_URL[] =
  "http://10.42.0.1:5057/api/bridge/v1";

static constexpr uint16_t PTP_CONTAINER_COMMAND = 1;
static constexpr uint16_t PTP_CONTAINER_DATA = 2;
static constexpr uint16_t PTP_CONTAINER_RESPONSE = 3;
static constexpr uint16_t PTP_OC_GET_DEVICE_INFO = 0x1001;
static constexpr uint16_t PTP_OC_OPEN_SESSION = 0x1002;
static constexpr uint16_t PTP_OC_CLOSE_SESSION = 0x1003;
static constexpr uint16_t PTP_OC_GET_STORAGE_IDS = 0x1004;
static constexpr uint16_t PTP_OC_GET_STORAGE_INFO = 0x1005;
static constexpr uint16_t PTP_OC_GET_OBJECT_HANDLES = 0x1007;
static constexpr uint16_t PTP_OC_GET_OBJECT_INFO = 0x1008;
static constexpr uint16_t PTP_OC_GET_PARTIAL_OBJECT = 0x101B;
static constexpr uint16_t PTP_RC_OK = 0x2001;
static constexpr uint16_t PTP_FORMAT_ASSOCIATION = 0x3001;

static constexpr size_t USB_BULK_BUFFER_SIZE = 16 * 1024;
static constexpr size_t MAX_METADATA_BYTES = 256 * 1024;
static constexpr size_t MAX_OBJECT_HANDLES = 16384;
static constexpr size_t QUICK_SAMPLE_SIZE = 64 * 1024;
// Upper bound; the server's preflight chunk_size can lower it. Two buffers of
// this size live in PSRAM while camera reads and uploads overlap.
static constexpr size_t UPLOAD_CHUNK_SIZE = 2 * 1024 * 1024;
static constexpr size_t MAX_SESSION_OBJECTS = 50;
static constexpr uint32_t BURST_FIRST_BYTES = 1024 * 1024;
static constexpr uint32_t BURST_PREVIEW_BYTES = 4 * 1024 * 1024;
static constexpr uint32_t SCAN_INTERVAL_MS = 5000;
static constexpr uint32_t PRIORITY_SCAN_INTERVAL_MS = 5000;
static constexpr uint32_t PRIMARY_STORAGE_ID = 0x00010001;
static constexpr uint32_t SECONDARY_STORAGE_ID = 0x00020001;
static constexpr uint32_t WIFI_TIMEOUT_MS = 25000;
static constexpr uint8_t HTTP_RETRIES = 4;

struct PtpContainerHeader {
  uint32_t length;
  uint16_t type;
  uint16_t code;
  uint32_t transaction;
};

struct TransferWaiter {
  SemaphoreHandle_t done = nullptr;
  usb_transfer_status_t status = USB_TRANSFER_STATUS_ERROR;
  size_t actual = 0;
};

struct CameraIdentity {
  String manufacturer;
  String model;
  String version;
  String serial;
  bool supportsPartialObject = false;
};

struct ObjectInfo {
  uint32_t handle = 0;
  uint32_t storageId = 0;
  uint16_t format = 0;
  uint32_t size = 0;
  uint32_t parent = 0;
  uint16_t associationType = 0;
  String filename;
  String capturedAt;
  String modifiedAt;
};

struct BridgeConfig {
  String ssid;
  String password;
  String serverUrl;
  String token;
};

struct HttpResult {
  int code = -1;
  String body;
};

struct PreflightResult {
  bool skip = false;
  String uploadId;
  uint32_t offset = 0;
  uint32_t chunkSize = UPLOAD_CHUNK_SIZE;
};

static Preferences gPreferences;
static SemaphoreHandle_t gConfigMutex = nullptr;
static BridgeConfig gConfig;
static String gSerialLine;
static volatile bool gForceRescan = false;

static usb_host_client_handle_t gClient = nullptr;
static usb_device_handle_t gDevice = nullptr;
static TaskHandle_t gWorkerTask = nullptr;

// One chunk travels over Wi-Fi while the next is read from the camera.
struct ChunkSend {
  const String *uploadId = nullptr;
  uint32_t start = 0;
  uint32_t total = 0;
  const std::vector<uint8_t> *chunk = nullptr;
  uint32_t nextOffset = 0;
  uint32_t readMs = 0;
  uint32_t sendMs = 0;
  bool ok = false;
};
static QueueHandle_t gChunkQueue = nullptr;
static SemaphoreHandle_t gChunkDone = nullptr;
static bool gPipelineReady = false;
static volatile int gPendingDeviceAddress = -1;
static volatile bool gDeviceGone = false;
static volatile bool gWorkerBusy = false;
static uint8_t gInterfaceNumber = 0;
static uint8_t gAlternateSetting = 0;
static uint8_t gBulkInEndpoint = 0;
static uint8_t gBulkOutEndpoint = 0;
static uint16_t gBulkInPacketSize = 64;
static bool gInterfaceClaimed = false;
static uint32_t gNextTransaction = 1;
static std::vector<uint32_t> gHandledHandles;
static std::vector<uint32_t> gInitialHandles;
static std::vector<uint32_t> gStagedHandles;
static bool gInitialHandlesReady = false;
static uint32_t gPausedHandle = 0;

enum class UploadResult { Complete, Staged, Paused, Failed };
static bool newHandlesWaiting(const std::vector<uint32_t> &knownHandles);

static uint16_t readLe16(const uint8_t *data) {
  return static_cast<uint16_t>(data[0]) |
         (static_cast<uint16_t>(data[1]) << 8);
}

static uint32_t readLe32(const uint8_t *data) {
  return static_cast<uint32_t>(data[0]) |
         (static_cast<uint32_t>(data[1]) << 8) |
         (static_cast<uint32_t>(data[2]) << 16) |
         (static_cast<uint32_t>(data[3]) << 24);
}

static void writeLe16(uint8_t *data, uint16_t value) {
  data[0] = static_cast<uint8_t>(value);
  data[1] = static_cast<uint8_t>(value >> 8);
}

static void writeLe32(uint8_t *data, uint32_t value) {
  data[0] = static_cast<uint8_t>(value);
  data[1] = static_cast<uint8_t>(value >> 8);
  data[2] = static_cast<uint8_t>(value >> 16);
  data[3] = static_cast<uint8_t>(value >> 24);
}

static String jsonEscape(const String &value) {
  String result;
  result.reserve(value.length() + 16);
  for (size_t i = 0; i < value.length(); ++i) {
    const char c = value[i];
    if (c == '"' || c == '\\') {
      result += '\\';
      result += c;
    } else if (c == '\n') {
      result += F("\\n");
    } else if (c == '\r') {
      result += F("\\r");
    } else if (static_cast<uint8_t>(c) >= 0x20) {
      result += c;
    }
  }
  return result;
}

static int jsonValueStart(const String &json, const char *key) {
  const String needle = String("\"") + key + "\"";
  int position = json.indexOf(needle);
  if (position < 0) return -1;
  position = json.indexOf(':', position + needle.length());
  if (position < 0) return -1;
  ++position;
  while (position < static_cast<int>(json.length()) &&
         isspace(static_cast<unsigned char>(json[position]))) {
    ++position;
  }
  return position;
}

static bool jsonString(const String &json, const char *key, String &value) {
  int position = jsonValueStart(json, key);
  if (position < 0 || json[position] != '"') return false;
  ++position;
  value = "";
  while (position < static_cast<int>(json.length())) {
    const char c = json[position++];
    if (c == '"') return true;
    if (c == '\\' && position < static_cast<int>(json.length())) {
      const char escaped = json[position++];
      if (escaped == 'n') value += '\n';
      else if (escaped == 'r') value += '\r';
      else if (escaped == 't') value += '\t';
      else value += escaped;
    } else {
      value += c;
    }
  }
  return false;
}

static bool jsonUnsigned(const String &json, const char *key, uint64_t &value) {
  const int position = jsonValueStart(json, key);
  if (position < 0) return false;
  char *end = nullptr;
  value = strtoull(json.c_str() + position, &end, 10);
  return end != json.c_str() + position;
}

static bool jsonBoolean(const String &json, const char *key, bool &value) {
  const int position = jsonValueStart(json, key);
  if (position < 0) return false;
  if (json.startsWith("true", position)) {
    value = true;
    return true;
  }
  if (json.startsWith("false", position)) {
    value = false;
    return true;
  }
  return false;
}

static String urlEncode(const String &value) {
  static const char hex[] = "0123456789ABCDEF";
  String encoded;
  encoded.reserve(value.length() * 3);
  for (size_t i = 0; i < value.length(); ++i) {
    const uint8_t c = static_cast<uint8_t>(value[i]);
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
        (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.') {
      encoded += static_cast<char>(c);
    } else {
      encoded += '%';
      encoded += hex[c >> 4];
      encoded += hex[c & 0x0F];
    }
  }
  return encoded;
}

static String normalizedServerUrl(String value) {
  value.trim();
  while (value.endsWith("/")) value.remove(value.length() - 1);
  return value;
}

static BridgeConfig configSnapshot() {
  BridgeConfig copy;
  xSemaphoreTake(gConfigMutex, portMAX_DELAY);
  copy = gConfig;
  xSemaphoreGive(gConfigMutex);
  return copy;
}

static void loadConfig() {
  gPreferences.begin("niwabridge", false);
  gConfig.ssid =
    gPreferences.getString("wifi_ssid", DEFAULT_WIFI_SSID);
  gConfig.password = gPreferences.getString("wifi_pass", "");
  gConfig.serverUrl = normalizedServerUrl(
    gPreferences.getString("api_url", DEFAULT_SERVER_URL)
  );
  gConfig.token = gPreferences.getString("api_token", "");
}

static void saveConfig() {
  const BridgeConfig config = configSnapshot();
  gPreferences.putString("wifi_ssid", config.ssid);
  gPreferences.putString("wifi_pass", config.password);
  gPreferences.putString("api_url", normalizedServerUrl(config.serverUrl));
  gPreferences.putString("api_token", config.token);
  Serial.println(F("[CONFIG] Saved to local ESP32 NVS storage."));
}

static String bridgeClientId() {
  const uint64_t id = ESP.getEfuseMac();
  char value[32];
  snprintf(value, sizeof(value), "esp32s3-%04X%08lX",
           static_cast<unsigned>((id >> 32) & 0xFFFF),
           static_cast<unsigned long>(id & 0xFFFFFFFF));
  return String(value);
}

static const char *authModeName(wifi_auth_mode_t mode) {
  switch (mode) {
    case WIFI_AUTH_OPEN: return "OPEN";
    case WIFI_AUTH_WEP: return "WEP";
    case WIFI_AUTH_WPA_PSK: return "WPA-PSK";
    case WIFI_AUTH_WPA2_PSK: return "WPA2-PSK";
    case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2-PSK";
    case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-ENTERPRISE";
    case WIFI_AUTH_WPA3_PSK: return "WPA3-PSK";
    case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3-PSK";
    case WIFI_AUTH_WAPI_PSK: return "WAPI-PSK";
    default: return "UNKNOWN";
  }
}

static void printWiFiScan() {
  Serial.println();
  Serial.println(F("============== NIWA WI-FI SCAN =========="));
  const int found = WiFi.scanNetworks(false, true);
  if (found <= 0) {
    Serial.println(F("No access point found (2.4 GHz only on this ESP32)."));
  } else {
    for (int i = 0; i < found; ++i) {
      Serial.printf("%2d) %-24s ch%-3d %4d dBm  %s\n",
                    i + 1,
                    WiFi.SSID(i).length() ? WiFi.SSID(i).c_str() : "(hidden)",
                    WiFi.channel(i),
                    WiFi.RSSI(i),
                    authModeName(WiFi.encryptionType(i)));
    }
  }
  WiFi.scanDelete();
  Serial.println(F("========================================="));
}

static void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    Serial.printf("[WIFI] Disconnected, reason %u.\n",
                  static_cast<unsigned>(info.wifi_sta_disconnected.reason));
  }
}

static void printStatus() {
  const BridgeConfig config = configSnapshot();
  Serial.println();
  Serial.println(F("============== NIWA STATUS =============="));
  Serial.printf("Firmware       : %s\n", FIRMWARE_VERSION);
  Serial.printf("Client ID      : %s\n", bridgeClientId().c_str());
  Serial.printf("Wi-Fi SSID     : %s\n",
                config.ssid.length() ? config.ssid.c_str() : "(missing)");
  Serial.printf("Wi-Fi password : %s (%u chars)\n",
                config.password.length() ? "configured" : "empty/open",
                static_cast<unsigned>(config.password.length()));
  Serial.printf("Server URL     : %s\n",
                config.serverUrl.length() ? config.serverUrl.c_str() : "(missing)");
  Serial.printf("Bridge token   : %s\n",
                config.token.length() ? "configured" : "empty");
  Serial.printf("Wi-Fi state    : %s\n",
                WiFi.status() == WL_CONNECTED ? "connected" : "disconnected");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("ESP32 IP       : %s\n", WiFi.localIP().toString().c_str());
  }
  Serial.printf("USB camera     : %s\n",
                gWorkerBusy && !gDeviceGone ? "connected/busy" : "waiting");
  Serial.println(F("========================================="));
}

static void setConfigValue(const char *field, const String &value) {
  xSemaphoreTake(gConfigMutex, portMAX_DELAY);
  if (strcmp(field, "ssid") == 0) gConfig.ssid = value;
  else if (strcmp(field, "password") == 0) gConfig.password = value;
  else if (strcmp(field, "url") == 0) {
    gConfig.serverUrl = normalizedServerUrl(value);
  } else if (strcmp(field, "token") == 0) gConfig.token = value;
  xSemaphoreGive(gConfigMutex);
}

static void commandWiFiConnect();

static void processSerialCommand(String command) {
  command.trim();
  if (!command.length()) return;

  if (command.startsWith("WIFI_SSID=")) {
    String value = command.substring(strlen("WIFI_SSID="));
    value.trim();
    setConfigValue("ssid", value);
    Serial.println(F("[CONFIG] Wi-Fi SSID updated in RAM. Send SAVE_CONFIG."));
  } else if (command.startsWith("WIFI_PASSWORD=")) {
    setConfigValue("password", command.substring(strlen("WIFI_PASSWORD=")));
    Serial.println(F("[CONFIG] Wi-Fi password updated (hidden). Send SAVE_CONFIG."));
  } else if (command.startsWith("SERVER_URL=")) {
    String value = command.substring(strlen("SERVER_URL="));
    value.trim();
    setConfigValue("url", value);
    Serial.println(F("[CONFIG] Server URL updated in RAM. Send SAVE_CONFIG."));
  } else if (command.startsWith("BRIDGE_TOKEN=")) {
    setConfigValue("token", command.substring(strlen("BRIDGE_TOKEN=")));
    Serial.println(F("[CONFIG] Bridge token updated (hidden). Send SAVE_CONFIG."));
  } else if (command == "SAVE_CONFIG") {
    saveConfig();
    WiFi.disconnect();
    gForceRescan = true;
  } else if (command == "STATUS") {
    printStatus();
  } else if (command == "WIFI_SCAN") {
    printWiFiScan();
  } else if (command == "WIFI_CONNECT") {
    commandWiFiConnect();
  } else if (command == "RESCAN") {
    gForceRescan = true;
    Serial.println(F("[NIWA] Rescan requested."));
  } else if (command == "CLEAR_CONFIG") {
    xSemaphoreTake(gConfigMutex, portMAX_DELAY);
    gConfig.ssid = DEFAULT_WIFI_SSID;
    gConfig.password = "";
    gConfig.serverUrl = DEFAULT_SERVER_URL;
    gConfig.token = "";
    xSemaphoreGive(gConfigMutex);
    saveConfig();
    WiFi.disconnect(true, false);
    Serial.println(F("[CONFIG] Restored defaults; credentials cleared."));
  } else if (command == "HELP") {
    Serial.println(F("Commands: WIFI_SSID=, WIFI_PASSWORD=, SERVER_URL=,"));
    Serial.println(F("          BRIDGE_TOKEN=, SAVE_CONFIG, STATUS, RESCAN,"));
    Serial.println(F("          WIFI_SCAN, WIFI_CONNECT, CLEAR_CONFIG"));
  } else {
    Serial.println(F("[CONFIG] Unknown command. Send HELP."));
  }
}

// The bridge normally joins Wi-Fi only when it has something to upload, so
// provisioning cannot be validated without a camera attached. This command
// forces one connection attempt on demand.
static void commandWiFiConnect() {
  const BridgeConfig config = configSnapshot();
  if (!config.ssid.length()) {
    Serial.println(F("[WIFI] Missing SSID. Configure it over Serial."));
    return;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Already connected, IP %s, RSSI %d dBm.\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    return;
  }

  Serial.printf("[WIFI] Connecting to %s", config.ssid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(config.ssid.c_str(), config.password.c_str());
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - started < WIFI_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Connected, IP %s, RSSI %d dBm.\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.printf("[WIFI] Connection failed (status %d).\n",
                  static_cast<int>(WiFi.status()));
  }
}

static bool ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  const BridgeConfig config = configSnapshot();
  if (!config.ssid.length()) {
    Serial.println(F("[WIFI] Missing SSID. Configure it over Serial."));
    return false;
  }

  Serial.printf("[WIFI] Connecting to %s", config.ssid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(config.ssid.c_str(), config.password.c_str());
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - started < WIFI_TIMEOUT_MS &&
         !gDeviceGone) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("[WIFI] Connection failed (status %d).\n",
                  static_cast<int>(WiFi.status()));
    return false;
  }
  Serial.printf("[WIFI] Connected, IP %s, RSSI %d dBm.\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

static void configureHttp(HTTPClient &http,
                          const BridgeConfig &config,
                          const String &contentType) {
  http.setConnectTimeout(6000);
  http.setTimeout(25000);
  http.setReuse(false);
  http.addHeader("Accept", "application/json");
  if (contentType.length()) http.addHeader("Content-Type", contentType);
  if (config.token.length()) {
    http.addHeader("Authorization", String("Bearer ") + config.token);
  }
  http.addHeader("X-NIWA-Client", bridgeClientId());
}

static bool httpJson(const char *method,
                     const String &path,
                     const String &payload,
                     HttpResult &result,
                     bool captureBody = true) {
  for (uint8_t attempt = 1; attempt <= HTTP_RETRIES && !gDeviceGone; ++attempt) {
    if (!ensureWiFi()) {
      delay(400 * attempt);
      continue;
    }
    const BridgeConfig config = configSnapshot();
    if (!config.serverUrl.startsWith("http://")) {
      Serial.println(F("[HTTP] SERVER_URL must use local http://."));
      return false;
    }
    HTTPClient http;
    const String url = config.serverUrl + path;
    if (!http.begin(url)) {
      Serial.println(F("[HTTP] Cannot open URL."));
      return false;
    }
    configureHttp(http, config, "application/json");
    int code = -1;
    if (strcmp(method, "GET") == 0) {
      code = http.GET();
    } else {
      code = http.sendRequest(method,
                              reinterpret_cast<uint8_t *>(
                                const_cast<char *>(payload.c_str())
                              ),
                              payload.length());
    }
    result.code = code;
    result.body = code > 0 && captureBody ? http.getString() : "";
    http.end();

    if (code >= 200 && code < 300) return true;
    if (code == 400 || code == 401 || code == 403 ||
        code == 404 || code == 409 || code == 413 || code == 422) {
      Serial.printf("[HTTP] %s %s -> %d\n", method, path.c_str(), code);
      return false;
    }
    Serial.printf("[HTTP] %s attempt %u/%u failed (%d).\n",
                  path.c_str(), attempt, HTTP_RETRIES, code);
    WiFi.disconnect();
    delay(500 * attempt);
  }
  return false;
}

class DatasetCursor {
 public:
  DatasetCursor(const uint8_t *data, size_t size)
      : data_(data), size_(size), offset_(0), valid_(true) {}

  bool valid() const { return valid_; }

  size_t remaining() const {
    return offset_ <= size_ ? size_ - offset_ : 0;
  }

  uint16_t u16() {
    if (!require(2)) return 0;
    const uint16_t value = readLe16(data_ + offset_);
    offset_ += 2;
    return value;
  }

  uint32_t u32() {
    if (!require(4)) return 0;
    const uint32_t value = readLe32(data_ + offset_);
    offset_ += 4;
    return value;
  }

  uint64_t u64() {
    if (!require(8)) return 0;
    const uint32_t low = u32();
    const uint32_t high = u32();
    return static_cast<uint64_t>(low) |
           (static_cast<uint64_t>(high) << 32);
  }

  String ptpString() {
    if (!require(1)) return String();
    const uint8_t count = data_[offset_++];
    if (count == 0) return String();
    const size_t bytes = static_cast<size_t>(count) * 2;
    if (!require(bytes)) return String();
    String result;
    result.reserve(count);
    for (uint8_t i = 0; i < count; ++i) {
      const uint16_t codePoint = readLe16(data_ + offset_ + i * 2);
      if (codePoint == 0) break;
      result += codePoint >= 0x20 && codePoint <= 0xFF
                  ? static_cast<char>(codePoint)
                  : '?';
    }
    offset_ += bytes;
    return result;
  }

  bool u16Array(std::vector<uint16_t> &values, size_t maximum = 4096) {
    const uint32_t count = u32();
    if (!valid_ || count > maximum || remaining() < count * 2ULL) {
      valid_ = false;
      return false;
    }
    values.clear();
    values.reserve(count);
    for (uint32_t i = 0; i < count; ++i) values.push_back(u16());
    return valid_;
  }

  bool u32Array(std::vector<uint32_t> &values, size_t maximum) {
    const uint32_t count = u32();
    if (!valid_ || count > maximum || remaining() < count * 4ULL) {
      valid_ = false;
      return false;
    }
    values.clear();
    values.reserve(count);
    for (uint32_t i = 0; i < count; ++i) values.push_back(u32());
    return valid_;
  }

 private:
  bool require(size_t amount) {
    if (!valid_ || amount > remaining()) {
      valid_ = false;
      return false;
    }
    return true;
  }

  const uint8_t *data_;
  size_t size_;
  size_t offset_;
  bool valid_;
};

static void transferCallback(usb_transfer_t *transfer) {
  TransferWaiter *waiter =
    static_cast<TransferWaiter *>(transfer->context);
  waiter->status = transfer->status;
  waiter->actual = transfer->actual_num_bytes;
  xSemaphoreGive(waiter->done);
}

static bool runBulkTransfer(uint8_t endpoint,
                            const uint8_t *output,
                            size_t outputLength,
                            uint8_t *input,
                            size_t inputCapacity,
                            size_t &actualLength) {
  actualLength = 0;
  if (gDeviceGone || gDevice == nullptr) return false;
  const bool isInput = (endpoint & 0x80) != 0;
  const size_t allocationSize = isInput ? inputCapacity : outputLength;
  if (allocationSize == 0) return false;

  usb_transfer_t *transfer = nullptr;
  esp_err_t result =
    usb_host_transfer_alloc(allocationSize, 0, &transfer);
  if (result != ESP_OK || transfer == nullptr) {
    Serial.printf("[USB] transfer_alloc: %s\n", esp_err_to_name(result));
    return false;
  }

  TransferWaiter waiter;
  waiter.done = xSemaphoreCreateBinary();
  if (waiter.done == nullptr) {
    usb_host_transfer_free(transfer);
    return false;
  }

  if (!isInput) memcpy(transfer->data_buffer, output, outputLength);
  transfer->device_handle = gDevice;
  transfer->bEndpointAddress = endpoint;
  transfer->callback = transferCallback;
  transfer->context = &waiter;
  transfer->num_bytes = allocationSize;

  result = usb_host_transfer_submit(transfer);
  if (result != ESP_OK) {
    Serial.printf("[USB] transfer_submit EP 0x%02X: %s\n",
                  endpoint, esp_err_to_name(result));
    vSemaphoreDelete(waiter.done);
    usb_host_transfer_free(transfer);
    return false;
  }

  // The callback owns a pointer to this waiter. Wait without a finite timeout
  // so the stack object cannot disappear before the host completes/cancels it.
  xSemaphoreTake(waiter.done, portMAX_DELAY);
  const bool completed = waiter.status == USB_TRANSFER_STATUS_COMPLETED;
  if (completed && isInput && waiter.actual) {
    memcpy(input, transfer->data_buffer, waiter.actual);
    actualLength = waiter.actual;
  } else if (completed) {
    actualLength = waiter.actual;
  } else {
    Serial.printf("[USB] EP 0x%02X transfer status %d.\n",
                  endpoint, static_cast<int>(waiter.status));
  }

  vSemaphoreDelete(waiter.done);
  usb_host_transfer_free(transfer);
  return completed;
}

class BulkReader {
 public:
  BulkReader() : buffer_(USB_BULK_BUFFER_SIZE), offset_(0), available_(0) {}

  void reset() {
    offset_ = 0;
    available_ = 0;
  }

  bool readExact(uint8_t *destination, size_t length) {
    size_t copied = 0;
    while (copied < length) {
      if (offset_ >= available_ && !refill()) return false;
      const size_t amount =
        min(length - copied, available_ - offset_);
      memcpy(destination + copied, buffer_.data() + offset_, amount);
      offset_ += amount;
      copied += amount;
    }
    return true;
  }

 private:
  bool refill() {
    for (uint8_t attempt = 0; attempt < 4; ++attempt) {
      size_t actual = 0;
      if (!runBulkTransfer(gBulkInEndpoint, nullptr, 0,
                           buffer_.data(), buffer_.size(), actual)) {
        return false;
      }
      if (actual) {
        offset_ = 0;
        available_ = actual;
        return true;
      }
    }
    Serial.println(F("[PTP] Too many empty Bulk IN packets."));
    return false;
  }

  std::vector<uint8_t> buffer_;
  size_t offset_;
  size_t available_;
};

static BulkReader gBulkReader;

static bool readContainerHeader(PtpContainerHeader &header) {
  uint8_t raw[12];
  if (!gBulkReader.readExact(raw, sizeof(raw))) return false;
  header.length = readLe32(raw);
  header.type = readLe16(raw + 4);
  header.code = readLe16(raw + 6);
  header.transaction = readLe32(raw + 8);
  if (header.length < 12) {
    Serial.printf("[PTP] Invalid container length %lu.\n",
                  static_cast<unsigned long>(header.length));
    return false;
  }
  return true;
}

static bool discardBytes(size_t length) {
  uint8_t scratch[256];
  while (length) {
    const size_t amount = min(length, sizeof(scratch));
    if (!gBulkReader.readExact(scratch, amount)) return false;
    length -= amount;
  }
  return true;
}

static bool sendCommand(uint16_t operation,
                        uint32_t transaction,
                        const uint32_t *parameters,
                        size_t parameterCount) {
  if (parameterCount > 5) return false;
  uint8_t command[12 + 5 * 4] = {};
  const size_t length = 12 + parameterCount * 4;
  writeLe32(command, static_cast<uint32_t>(length));
  writeLe16(command + 4, PTP_CONTAINER_COMMAND);
  writeLe16(command + 6, operation);
  writeLe32(command + 8, transaction);
  for (size_t i = 0; i < parameterCount; ++i) {
    writeLe32(command + 12 + i * 4, parameters[i]);
  }
  size_t actual = 0;
  return runBulkTransfer(gBulkOutEndpoint, command, length,
                         nullptr, 0, actual) &&
         actual == length;
}

static bool readResponse(uint32_t transaction, uint16_t &responseCode) {
  PtpContainerHeader response;
  if (!readContainerHeader(response)) return false;
  if (response.type != PTP_CONTAINER_RESPONSE ||
      response.transaction != transaction) {
    Serial.printf("[PTP] Unexpected response type=%u code=0x%04X tx=%lu.\n",
                  response.type, response.code,
                  static_cast<unsigned long>(response.transaction));
    if (response.length > 12) discardBytes(response.length - 12);
    return false;
  }
  if (response.length > 12 && !discardBytes(response.length - 12)) {
    return false;
  }
  responseCode = response.code;
  return true;
}

static bool commandWithoutData(uint16_t operation,
                               uint32_t transaction,
                               const uint32_t *parameters,
                               size_t parameterCount) {
  if (!sendCommand(operation, transaction, parameters, parameterCount)) {
    return false;
  }
  uint16_t response = 0;
  if (!readResponse(transaction, response)) return false;
  if (response != PTP_RC_OK) {
    Serial.printf("[PTP] Operation 0x%04X failed: response 0x%04X.\n",
                  operation, response);
    return false;
  }
  return true;
}

static bool commandWithData(uint16_t operation,
                            uint32_t transaction,
                            const uint32_t *parameters,
                            size_t parameterCount,
                            std::vector<uint8_t> &payload,
                            size_t maximumBytes) {
  payload.clear();
  if (!sendCommand(operation, transaction, parameters, parameterCount)) {
    return false;
  }
  PtpContainerHeader dataHeader;
  if (!readContainerHeader(dataHeader)) return false;
  if (dataHeader.type == PTP_CONTAINER_RESPONSE) {
    if (dataHeader.length > 12) discardBytes(dataHeader.length - 12);
    Serial.printf("[PTP] Operation 0x%04X returned response 0x%04X.\n",
                  operation, dataHeader.code);
    return false;
  }
  if (dataHeader.type != PTP_CONTAINER_DATA ||
      dataHeader.code != operation ||
      dataHeader.transaction != transaction) {
    Serial.printf("[PTP] Invalid data header for operation 0x%04X.\n",
                  operation);
    if (dataHeader.length > 12) discardBytes(dataHeader.length - 12);
    return false;
  }
  const size_t length = dataHeader.length - 12;
  if (length > maximumBytes) {
    Serial.printf("[PTP] Payload too large: %u > %u.\n",
                  static_cast<unsigned>(length),
                  static_cast<unsigned>(maximumBytes));
    discardBytes(length);
    uint16_t ignored = 0;
    readResponse(transaction, ignored);
    return false;
  }
  payload.resize(length);
  if (length && !gBulkReader.readExact(payload.data(), length)) return false;
  uint16_t response = 0;
  return readResponse(transaction, response) && response == PTP_RC_OK;
}

static bool getPartialObject(uint32_t handle,
                             uint32_t offset,
                             uint32_t requested,
                             std::vector<uint8_t> &payload) {
  const uint32_t parameters[3] = {handle, offset, requested};
  return commandWithData(PTP_OC_GET_PARTIAL_OBJECT,
                         gNextTransaction++,
                         parameters, 3, payload,
                         static_cast<size_t>(requested));
}

static bool parseDeviceInfo(const std::vector<uint8_t> &payload,
                            CameraIdentity &camera) {
  DatasetCursor cursor(payload.data(), payload.size());
  cursor.u16();       // StandardVersion
  cursor.u32();       // VendorExtensionID
  cursor.u16();       // VendorExtensionVersion
  cursor.ptpString(); // VendorExtensionDesc
  cursor.u16();       // FunctionalMode
  std::vector<uint16_t> operations;
  std::vector<uint16_t> ignored;
  cursor.u16Array(operations);
  cursor.u16Array(ignored); // EventsSupported
  cursor.u16Array(ignored); // DevicePropertiesSupported
  cursor.u16Array(ignored); // CaptureFormats
  cursor.u16Array(ignored); // ImageFormats
  camera.manufacturer = cursor.ptpString();
  camera.model = cursor.ptpString();
  camera.version = cursor.ptpString();
  camera.serial = cursor.ptpString();
  if (!cursor.valid()) {
    Serial.println(F("[PTP] Invalid DeviceInfo dataset."));
    return false;
  }
  camera.supportsPartialObject = false;
  for (uint16_t operation : operations) {
    if (operation == PTP_OC_GET_PARTIAL_OBJECT) {
      camera.supportsPartialObject = true;
    }
  }
  Serial.printf("[PTP] Camera: %s %s, firmware %s, serial %s.\n",
                camera.manufacturer.c_str(), camera.model.c_str(),
                camera.version.c_str(),
                camera.serial.length() ? camera.serial.c_str() : "(not exposed)");
  Serial.printf("[PTP] GetPartialObject: %s.\n",
                camera.supportsPartialObject ? "supported" : "NOT SUPPORTED");
  return true;
}

static bool parseObjectInfo(const std::vector<uint8_t> &payload,
                            uint32_t handle,
                            ObjectInfo &object) {
  if (payload.size() < 52) return false;
  DatasetCursor cursor(payload.data(), payload.size());
  object.handle = handle;
  object.storageId = cursor.u32();
  object.format = cursor.u16();
  cursor.u16(); // ProtectionStatus
  object.size = cursor.u32();
  cursor.u16(); // ThumbFormat
  cursor.u32(); // ThumbCompressedSize
  cursor.u32(); // ThumbPixWidth
  cursor.u32(); // ThumbPixHeight
  cursor.u32(); // ImagePixWidth
  cursor.u32(); // ImagePixHeight
  cursor.u32(); // ImageBitDepth
  object.parent = cursor.u32();
  object.associationType = cursor.u16();
  cursor.u32(); // AssociationDesc
  cursor.u32(); // SequenceNumber
  object.filename = cursor.ptpString();
  object.capturedAt = cursor.ptpString();
  object.modifiedAt = cursor.ptpString();
  cursor.ptpString(); // Keywords
  return cursor.valid();
}

static bool isPhoto(const ObjectInfo &object) {
  if (object.format == PTP_FORMAT_ASSOCIATION || object.size == 0) return false;
  String name = object.filename;
  name.toLowerCase();
  return name.endsWith(".nef") ||
         name.endsWith(".jpg") ||
         name.endsWith(".jpeg");
}

static bool handledContains(uint32_t handle) {
  return std::binary_search(gHandledHandles.begin(), gHandledHandles.end(),
                            handle);
}

static void markHandled(uint32_t handle) {
  gStagedHandles.erase(
    std::remove(gStagedHandles.begin(), gStagedHandles.end(), handle),
    gStagedHandles.end());
  auto position = std::lower_bound(gHandledHandles.begin(),
                                   gHandledHandles.end(), handle);
  if (position == gHandledHandles.end() || *position != handle)
    gHandledHandles.insert(position, handle);
}

static bool isNewHandle(uint32_t handle) {
  return gInitialHandlesReady &&
         !std::binary_search(gInitialHandles.begin(), gInitialHandles.end(),
                             handle);
}

static bool findPtpInterface() {
  const usb_config_desc_t *configuration = nullptr;
  esp_err_t result =
    usb_host_get_active_config_descriptor(gDevice, &configuration);
  if (result != ESP_OK || configuration == nullptr) {
    Serial.printf("[USB] Config descriptor: %s.\n", esp_err_to_name(result));
    return false;
  }

  const uint8_t *cursor =
    reinterpret_cast<const uint8_t *>(configuration);
  const uint8_t *end = cursor + configuration->wTotalLength;
  bool insidePtp = false;
  bool foundPtp = false;
  gBulkInEndpoint = 0;
  gBulkOutEndpoint = 0;
  gBulkInPacketSize = 64;

  while (cursor + 2 <= end) {
    const uint8_t length = cursor[0];
    const uint8_t type = cursor[1];
    if (length < 2 || cursor + length > end) break;

    if (type == USB_B_DESCRIPTOR_TYPE_INTERFACE &&
        length >= sizeof(usb_intf_desc_t)) {
      const usb_intf_desc_t *interfaceDescriptor =
        reinterpret_cast<const usb_intf_desc_t *>(cursor);
      insidePtp =
        interfaceDescriptor->bInterfaceClass == 0x06 &&
        interfaceDescriptor->bInterfaceSubClass == 0x01 &&
        interfaceDescriptor->bInterfaceProtocol == 0x01;
      if (insidePtp) {
        foundPtp = true;
        gInterfaceNumber = interfaceDescriptor->bInterfaceNumber;
        gAlternateSetting = interfaceDescriptor->bAlternateSetting;
      }
    } else if (insidePtp &&
               type == USB_B_DESCRIPTOR_TYPE_ENDPOINT &&
               length >= sizeof(usb_ep_desc_t)) {
      const usb_ep_desc_t *endpoint =
        reinterpret_cast<const usb_ep_desc_t *>(cursor);
      if ((endpoint->bmAttributes & 0x03) == 0x02) {
        if (endpoint->bEndpointAddress & 0x80) {
          gBulkInEndpoint = endpoint->bEndpointAddress;
          gBulkInPacketSize = endpoint->wMaxPacketSize & 0x07FF;
        } else {
          gBulkOutEndpoint = endpoint->bEndpointAddress;
        }
      }
    }
    cursor += length;
  }

  if (!foundPtp || !gBulkInEndpoint || !gBulkOutEndpoint) {
    Serial.println(F("[USB] Complete PTP bulk interface not found."));
    return false;
  }
  Serial.printf("[USB] PTP interface %u alt %u, OUT 0x%02X, IN 0x%02X, MPS %u.\n",
                gInterfaceNumber, gAlternateSetting,
                gBulkOutEndpoint, gBulkInEndpoint, gBulkInPacketSize);
  return true;
}

static String bytesToHex(const uint8_t *data, size_t length) {
  static const char digits[] = "0123456789abcdef";
  String result;
  result.reserve(length * 2);
  for (size_t i = 0; i < length; ++i) {
    result += digits[data[i] >> 4];
    result += digits[data[i] & 0x0F];
  }
  return result;
}

static bool quickFingerprint(const ObjectInfo &object, String &hash) {
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  if (mbedtls_sha256_starts(&context, 0) != 0) {
    mbedtls_sha256_free(&context);
    return false;
  }

  const String asciiSize = String(object.size);
  mbedtls_sha256_update(
    &context,
    reinterpret_cast<const unsigned char *>(asciiSize.c_str()),
    asciiSize.length()
  );

  uint32_t offsets[3] = {0, 0, 0};
  size_t offsetCount = 1;
  if (object.size > QUICK_SAMPLE_SIZE) {
    offsets[offsetCount++] =
      object.size / 2 - static_cast<uint32_t>(QUICK_SAMPLE_SIZE / 2);
    offsets[offsetCount++] =
      object.size - static_cast<uint32_t>(QUICK_SAMPLE_SIZE);
  }

  // Python uses a sorted set of offsets. Sort and collapse duplicates exactly.
  for (size_t i = 0; i < offsetCount; ++i) {
    for (size_t j = i + 1; j < offsetCount; ++j) {
      if (offsets[j] < offsets[i]) {
        const uint32_t temporary = offsets[i];
        offsets[i] = offsets[j];
        offsets[j] = temporary;
      }
    }
  }

  std::vector<uint8_t> sample;
  uint32_t previous = UINT32_MAX;
  for (size_t i = 0; i < offsetCount; ++i) {
    const uint32_t offset = offsets[i];
    if (offset == previous) continue;
    previous = offset;
    const uint32_t wanted =
      min(static_cast<uint32_t>(QUICK_SAMPLE_SIZE),
          object.size - offset);
    Serial.printf("[HASH] %s sample at %lu (%lu bytes).\n",
                  object.filename.c_str(),
                  static_cast<unsigned long>(offset),
                  static_cast<unsigned long>(wanted));
    if (!getPartialObject(object.handle, offset, wanted, sample) ||
        sample.size() != wanted) {
      Serial.println(F("[HASH] Camera sample read failed."));
      mbedtls_sha256_free(&context);
      return false;
    }
    mbedtls_sha256_update(&context, sample.data(), sample.size());
  }

  uint8_t digest[32];
  if (mbedtls_sha256_finish(&context, digest) != 0) {
    mbedtls_sha256_free(&context);
    return false;
  }
  mbedtls_sha256_free(&context);
  hash = bytesToHex(digest, sizeof(digest));
  return true;
}

static String cameraSourceId(const CameraIdentity &camera) {
  if (camera.serial.length()) return String("nikon-") + camera.serial;
  return String("nikon-") + camera.model + "-" + bridgeClientId();
}

static bool createApiSession(const CameraIdentity &camera,
                             String &sessionId) {
  const String payload =
    String("{\"source_id\":\"") + jsonEscape(cameraSourceId(camera)) +
    "\",\"camera_serial\":\"" + jsonEscape(camera.serial) +
    "\",\"camera_model\":\"" + jsonEscape(camera.model) +
    "\",\"client_id\":\"" + jsonEscape(bridgeClientId()) +
    "\",\"firmware_version\":\"" + FIRMWARE_VERSION + "\"}";
  HttpResult response;
  if (!httpJson("POST", "/sessions", payload, response) ||
      !jsonString(response.body, "session_id", sessionId) ||
      !sessionId.length()) {
    Serial.printf("[API] Cannot create import session (HTTP %d).\n",
                  response.code);
    return false;
  }
  Serial.printf("[API] Session %s opened.\n", sessionId.c_str());
  return true;
}

static String sourceKeyFor(const CameraIdentity &camera,
                           const ObjectInfo &object) {
  return cameraSourceId(camera) + "|" +
         String(object.storageId, HEX) + "|" +
         object.filename + "|" + String(object.size) + "|" +
         object.capturedAt;
}

static String objectIdFor(const CameraIdentity &camera,
                          const ObjectInfo &object,
                          const String &quickHash) {
  const String identity = sourceKeyFor(camera, object) + "|" + quickHash;
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  if (mbedtls_sha256_starts(&context, 0) != 0) {
    mbedtls_sha256_free(&context);
    return quickHash.substring(0, 40);
  }
  mbedtls_sha256_update(
    &context,
    reinterpret_cast<const unsigned char *>(identity.c_str()),
    identity.length()
  );
  uint8_t digest[32];
  if (mbedtls_sha256_finish(&context, digest) != 0) {
    mbedtls_sha256_free(&context);
    return quickHash.substring(0, 40);
  }
  mbedtls_sha256_free(&context);
  return bytesToHex(digest, sizeof(digest)).substring(0, 40);
}

static bool preflightObject(const String &sessionId,
                            const CameraIdentity &camera,
                            const ObjectInfo &object,
                            const String &quickHash,
                            PreflightResult &preflight) {
  const String payload =
    String("{\"object_id\":\"") +
    jsonEscape(objectIdFor(camera, object, quickHash)) +
    "\",\"source_key\":\"" +
    jsonEscape(sourceKeyFor(camera, object)) +
    "\",\"filename\":\"" + jsonEscape(object.filename) +
    "\",\"size\":" + String(object.size) +
    ",\"quick_hash\":\"" + quickHash +
    "\",\"captured_at\":\"" + jsonEscape(object.capturedAt) +
    "\",\"modified_at\":\"" + jsonEscape(object.modifiedAt) + "\"}";

  HttpResult response;
  const String path =
    String("/sessions/") + urlEncode(sessionId) + "/objects/preflight";
  if (!httpJson("POST", path, payload, response)) {
    Serial.printf("[API] Preflight failed for %s (HTTP %d).\n",
                  object.filename.c_str(), response.code);
    return false;
  }

  String action;
  if (!jsonString(response.body, "action", action)) {
    Serial.println(F("[API] Preflight response has no action."));
    return false;
  }
  if (action == "skip") {
    preflight.skip = true;
    preflight.offset = object.size;
    Serial.printf("[SKIP] %s already exists on the SSD.\n",
                  object.filename.c_str());
    return true;
  }
  if (action != "upload" ||
      !jsonString(response.body, "upload_id", preflight.uploadId) ||
      !preflight.uploadId.length()) {
    Serial.printf("[API] Unsupported preflight action: %s.\n", action.c_str());
    return false;
  }
  uint64_t numeric = 0;
  if (jsonUnsigned(response.body, "offset", numeric)) {
    if (numeric > object.size) return false;
    preflight.offset = static_cast<uint32_t>(numeric);
  }
  if (jsonUnsigned(response.body, "chunk_size", numeric) && numeric > 0) {
    preflight.chunkSize =
      static_cast<uint32_t>(min<uint64_t>(numeric, UPLOAD_CHUNK_SIZE));
  }
  Serial.printf("[API] Upload %s from offset %lu, chunk %lu.\n",
                object.filename.c_str(),
                static_cast<unsigned long>(preflight.offset),
                static_cast<unsigned long>(preflight.chunkSize));
  return true;
}

static bool getServerUploadOffset(const String &uploadId,
                                  uint32_t fileSize,
                                  uint32_t &offset) {
  HttpResult response;
  const String path = String("/uploads/") + urlEncode(uploadId);
  if (!httpJson("GET", path, "", response)) return false;
  uint64_t numeric = 0;
  if (!jsonUnsigned(response.body, "offset", numeric) ||
      numeric > fileSize) {
    return false;
  }
  offset = static_cast<uint32_t>(numeric);
  return true;
}

static bool putChunk(const String &uploadId,
                     uint32_t start,
                     uint32_t total,
                     const std::vector<uint8_t> &chunk,
                     uint32_t &nextOffset) {
  const uint32_t expected =
    start + static_cast<uint32_t>(chunk.size());
  const String path = String("/uploads/") + urlEncode(uploadId);

  for (uint8_t attempt = 1; attempt <= HTTP_RETRIES; ++attempt) {
    if (!ensureWiFi()) {
      delay(400 * attempt);
      continue;
    }
    const BridgeConfig config = configSnapshot();
    HTTPClient http;
    if (!http.begin(config.serverUrl + path)) return false;
    configureHttp(http, config, "application/octet-stream");
    http.addHeader(
      "Content-Range",
      String("bytes ") + String(start) + "-" +
      String(expected - 1) + "/" + String(total)
    );
    const int code = http.sendRequest(
      "PUT",
      const_cast<uint8_t *>(chunk.data()),
      chunk.size()
    );
    const String body = code > 0 ? http.getString() : "";
    http.end();

    uint64_t numeric = 0;
    if (code >= 200 && code < 300) {
      nextOffset = expected;
      if (jsonUnsigned(body, "offset", numeric) && numeric <= total) {
        nextOffset = static_cast<uint32_t>(numeric);
      }
      return nextOffset == expected;
    }

    if (code == 409 &&
        jsonUnsigned(body, "expected_offset", numeric) &&
        numeric <= total) {
      nextOffset = static_cast<uint32_t>(numeric);
      if (nextOffset == expected) {
        Serial.println(F("[HTTP] Server already has the chunk; continuing."));
        return true;
      }
      if (nextOffset != start) {
        Serial.printf("[HTTP] Unexpected server offset %lu (wanted %lu).\n",
                      static_cast<unsigned long>(nextOffset),
                      static_cast<unsigned long>(start));
        return false;
      }
    } else if (code == 400 || code == 401 || code == 403 ||
               code == 404 || code == 413 || code == 422) {
      Serial.printf("[HTTP] Chunk rejected with HTTP %d.\n", code);
      return false;
    }

    // A lost HTTP response can hide a successful append. Query the durable
    // server offset before resending the exact same bytes.
    uint32_t durableOffset = start;
    if (getServerUploadOffset(uploadId, total, durableOffset) &&
        durableOffset == expected) {
      nextOffset = durableOffset;
      Serial.println(F("[HTTP] Lost response recovered from server status."));
      return true;
    }
    if (durableOffset != start) {
      Serial.printf("[HTTP] Unsafe partial offset %lu; stopping this upload.\n",
                    static_cast<unsigned long>(durableOffset));
      return false;
    }
    Serial.printf("[HTTP] Chunk retry %u/%u.\n", attempt, HTTP_RETRIES);
    delay(500 * attempt);
  }
  return false;
}

static bool completeUpload(const String &uploadId,
                           const String &sha256) {
  const String payload =
    sha256.length()
      ? String("{\"sha256\":\"") + sha256 + "\"}"
      : String("{}");
  HttpResult response;
  const String path =
    String("/uploads/") + urlEncode(uploadId) + "/complete";
  if (!httpJson("POST", path, payload, response)) {
    Serial.printf("[API] Upload verification failed (HTTP %d).\n",
                  response.code);
    return false;
  }
  bool ok = true;
  if (jsonBoolean(response.body, "ok", ok) && !ok) return false;
  return true;
}

static void runChunkSend(ChunkSend &job) {
  const uint32_t started = millis();
  job.ok = putChunk(*job.uploadId, job.start, job.total,
                    *job.chunk, job.nextOffset);
  job.sendMs = millis() - started;
}

static void chunkSenderTask(void *argument) {
  (void)argument;
  ChunkSend *job = nullptr;
  while (true) {
    if (xQueueReceive(gChunkQueue, &job, portMAX_DELAY) == pdTRUE) {
      runChunkSend(*job);
      xSemaphoreGive(gChunkDone);
    }
  }
}

static UploadResult uploadObject(const ObjectInfo &object,
                                 const PreflightResult &preflight,
                                 const std::vector<uint32_t> &knownHandles,
                                 uint32_t stageBytes = 0) {
  if (preflight.skip) return UploadResult::Complete;
  uint32_t offset = preflight.offset;
  if (offset > object.size) return UploadResult::Failed;
  const uint32_t stopAt = stageBytes ? min(object.size, stageBytes) : object.size;
  if (offset >= stopAt && offset < object.size) return UploadResult::Staged;

  const bool clientHashAvailable = offset == 0;
  mbedtls_sha256_context hashContext;
  if (clientHashAvailable) {
    mbedtls_sha256_init(&hashContext);
    if (mbedtls_sha256_starts(&hashContext, 0) != 0) {
      mbedtls_sha256_free(&hashContext);
      return UploadResult::Failed;
    }
  } else {
    Serial.println(F("[HASH] Resuming after offset 0: server SHA-256 is authoritative."));
  }

  // Two buffers: the camera fills one while the other is on the air. At most
  // one chunk is in flight, so the server still receives offsets in order, and
  // a buffer is reused only after its upload is confirmed.
  std::vector<uint8_t> buffers[2];
  uint8_t filling = 0;
  ChunkSend job;
  bool inFlight = false;
  uint32_t lastDone = millis();
  uint32_t lastPriorityScan = millis();
  uint32_t readOffset = offset;

  // Waits for the chunk in flight and checks the server took it all. Must run
  // before returning: the sender task is still reading that buffer.
  auto finishInFlight = [&]() -> bool {
    if (!inFlight) return true;
    if (gPipelineReady) xSemaphoreTake(gChunkDone, portMAX_DELAY);
    inFlight = false;
    const uint32_t expected =
      job.start + static_cast<uint32_t>(job.chunk->size());
    if (!job.ok || job.nextOffset != expected) return false;
    offset = expected;
    const uint32_t now = millis();
    const unsigned percent =
      object.size ? static_cast<unsigned>(
        (static_cast<uint64_t>(offset) * 100ULL) / object.size
      ) : 100;
    // usb and wifi overlap now; cycle is the real time per chunk.
    Serial.printf("[UPLOAD] %s: %u%% (%lu/%lu), usb %lu ms, wifi %lu ms, "
                  "cycle %lu ms.\n",
                  object.filename.c_str(), percent,
                  static_cast<unsigned long>(offset),
                  static_cast<unsigned long>(object.size),
                  static_cast<unsigned long>(job.readMs),
                  static_cast<unsigned long>(job.sendMs),
                  static_cast<unsigned long>(now - lastDone));
    lastDone = now;
    return true;
  };

  bool success = true;
  bool paused = false;
  while (readOffset < stopAt && !gDeviceGone) {
    uint32_t requested = min(preflight.chunkSize, stopAt - readOffset);
    if (isNewHandle(object.handle) && readOffset < BURST_FIRST_BYTES)
      requested = min(requested, BURST_FIRST_BYTES - readOffset);
    std::vector<uint8_t> &chunk = buffers[filling];
    const uint32_t readStarted = millis();
    if (!getPartialObject(object.handle, readOffset, requested, chunk) ||
        chunk.empty() || chunk.size() > requested) {
      Serial.printf("[PTP] Read failed for %s at %lu.\n",
                    object.filename.c_str(),
                    static_cast<unsigned long>(readOffset));
      success = false;
      break;
    }
    const uint32_t readMs = millis() - readStarted;

    // Hash camera bytes once. HTTP retries reuse this buffer and must never
    // feed the same chunk into SHA-256 twice.
    if (clientHashAvailable) {
      mbedtls_sha256_update(&hashContext, chunk.data(), chunk.size());
    }

    if (!finishInFlight()) {
      success = false;
      break;
    }
    if (offset < object.size &&
        millis() - lastPriorityScan >= PRIORITY_SCAN_INTERVAL_MS) {
      lastPriorityScan = millis();
      if (newHandlesWaiting(knownHandles)) {
        Serial.printf("[PRIORITY] Pausing %s at durable offset %lu.\n",
                      object.filename.c_str(),
                      static_cast<unsigned long>(offset));
        paused = true;
        break;
      }
    }
    job = ChunkSend();
    job.uploadId = &preflight.uploadId;
    job.start = readOffset;
    job.total = object.size;
    job.chunk = &chunk;
    job.readMs = readMs;
    inFlight = true;
    if (gPipelineReady) {
      ChunkSend *queued = &job;
      xQueueSend(gChunkQueue, &queued, portMAX_DELAY);
    } else {
      runChunkSend(job);  // no sender task: plain sequential upload
    }
    readOffset += static_cast<uint32_t>(chunk.size());
    filling ^= 1;
  }
  if (!finishInFlight()) success = false;

  String fullHash;
  if (clientHashAvailable) {
    if (success && offset == object.size) {
      uint8_t digest[32];
      if (mbedtls_sha256_finish(&hashContext, digest) != 0) {
        success = false;
      } else {
        fullHash = bytesToHex(digest, sizeof(digest));
      }
    }
    mbedtls_sha256_free(&hashContext);
  }
  if (paused) return UploadResult::Paused;
  if (success && offset == stopAt && stopAt < object.size)
    return UploadResult::Staged;
  if (!success || offset != object.size) return UploadResult::Failed;
  if (!completeUpload(preflight.uploadId, fullHash)) return UploadResult::Failed;
  Serial.printf("[VERIFY] %s verified by Raspberry SHA-256.\n",
                object.filename.c_str());
  return UploadResult::Complete;
}

static bool completeApiSession(const String &sessionId) {
  HttpResult response;
  const String path =
    String("/sessions/") + urlEncode(sessionId) + "/complete";
  if (!httpJson("POST", path, "{}", response, false)) {
    Serial.printf("[API] Session completion failed (HTTP %d).\n",
                  response.code);
    return false;
  }
  Serial.printf("[API] Session %s published on SSD.\n", sessionId.c_str());
  return true;
}

static bool getStorageIds(std::vector<uint32_t> &storageIds) {
  std::vector<uint8_t> payload;
  if (!commandWithData(PTP_OC_GET_STORAGE_IDS, gNextTransaction++,
                       nullptr, 0, payload, MAX_METADATA_BYTES)) {
    return false;
  }
  DatasetCursor cursor(payload.data(), payload.size());
  return cursor.u32Array(storageIds, 16);
}

static bool getObjectHandles(uint32_t storageId,
                             std::vector<uint32_t> &handles) {
  const uint32_t parameters[3] = {storageId, 0, 0};
  std::vector<uint8_t> payload;
  if (!commandWithData(PTP_OC_GET_OBJECT_HANDLES, gNextTransaction++,
                       parameters, 3, payload, MAX_METADATA_BYTES)) {
    return false;
  }
  DatasetCursor cursor(payload.data(), payload.size());
  return cursor.u32Array(handles, MAX_OBJECT_HANDLES);
}

static bool getObjectInfo(uint32_t handle, ObjectInfo &object) {
  std::vector<uint8_t> payload;
  if (!commandWithData(PTP_OC_GET_OBJECT_INFO, gNextTransaction++,
                       &handle, 1, payload, MAX_METADATA_BYTES)) {
    return false;
  }
  return parseObjectInfo(payload, handle, object);
}

static bool collectCameraHandles(std::vector<uint32_t> &handles,
                                 std::vector<uint32_t> *baseline = nullptr) {
  std::vector<uint32_t> storageIds;
  if (!getStorageIds(storageIds)) {
    Serial.println(F("[SCAN] Cannot read camera storages."));
    return false;
  }
  const bool primaryPresent =
    std::find(storageIds.begin(), storageIds.end(), PRIMARY_STORAGE_ID) !=
    storageIds.end();
  const uint32_t selectedStorage = primaryPresent ? PRIMARY_STORAGE_ID :
    (std::find(storageIds.begin(), storageIds.end(), SECONDARY_STORAGE_ID) !=
     storageIds.end() ? SECONDARY_STORAGE_ID : 0);
  if (!selectedStorage) {
    Serial.println(F("[SCAN] No Nikon card available; nothing to import."));
    return false;
  }
  Serial.printf("[SCAN] Importing slot %u%s.\n",
                selectedStorage == PRIMARY_STORAGE_ID ? 1 : 2,
                primaryPresent ? "" : " (slot 1 absent)");
  for (uint32_t storageId : storageIds) {
    if (storageId != selectedStorage && !baseline) continue;
    std::vector<uint32_t> storageHandles;
    if (!getObjectHandles(storageId, storageHandles)) {
      Serial.printf("[SCAN] Cannot read storage 0x%08lX.\n",
                    static_cast<unsigned long>(storageId));
      if (storageId == selectedStorage) return false;
      continue;
    }
    Serial.printf("[SCAN] Storage 0x%08lX: %u objects.\n",
                  static_cast<unsigned long>(storageId),
                  static_cast<unsigned>(storageHandles.size()));
    if (baseline)
      baseline->insert(baseline->end(), storageHandles.begin(),
                       storageHandles.end());
    if (storageId == selectedStorage)
      handles = std::move(storageHandles);
  }
  return true;
}

static bool newHandlesWaiting(const std::vector<uint32_t> &knownHandles) {
  if (!gInitialHandlesReady) return false;
  std::vector<uint32_t> handles;
  if (!collectCameraHandles(handles)) return false;
  for (uint32_t handle : handles) {
    if (!isNewHandle(handle) || handledContains(handle) ||
        std::find(knownHandles.begin(), knownHandles.end(), handle) !=
          knownHandles.end()) continue;
    ObjectInfo object;
    if (getObjectInfo(handle, object) && isPhoto(object)) return true;
  }
  return false;
}

static bool scanCamera(const CameraIdentity &camera,
                       String &apiSessionId,
                       bool &sessionHasObjects,
                       size_t &sessionObjectCount) {
  // A checkpoint response may be lost after the Raspberry has already
  // committed the session. Retry this idempotent completion before issuing
  // any new preflight against a session that may no longer be active.
  if (apiSessionId.length() && sessionHasObjects && !gPausedHandle &&
      gStagedHandles.empty() &&
      sessionObjectCount >= MAX_SESSION_OBJECTS) {
    Serial.printf("[API] Recovering checkpoint batch (%u objects).\n",
                  static_cast<unsigned>(sessionObjectCount));
    if (!completeApiSession(apiSessionId)) {
      Serial.println(F("[API] Checkpoint recovery pending; scan deferred."));
      return false;
    }
    apiSessionId = "";
    sessionHasObjects = false;
    sessionObjectCount = 0;
  }

  std::vector<uint32_t> handles;
  std::vector<uint32_t> initialHandles;
  if (!collectCameraHandles(handles,
                            gInitialHandlesReady ? nullptr : &initialHandles))
    return false;
  gStagedHandles.erase(std::remove_if(
    gStagedHandles.begin(), gStagedHandles.end(),
    [&handles](uint32_t staged) {
      return std::find(handles.begin(), handles.end(), staged) == handles.end();
    }), gStagedHandles.end());
  if (gPausedHandle &&
      std::find(handles.begin(), handles.end(), gPausedHandle) == handles.end())
    gPausedHandle = 0;
  if (!gInitialHandlesReady) {
    gInitialHandles = std::move(initialHandles);
    std::sort(gInitialHandles.begin(), gInitialHandles.end());
    gInitialHandles.erase(
      std::unique(gInitialHandles.begin(), gInitialHandles.end()),
      gInitialHandles.end());
    gInitialHandlesReady = true;
    Serial.printf("[PRIORITY] Baseline: %u existing objects.\n",
                  static_cast<unsigned>(gInitialHandles.size()));
  }

  // New captures on the selected card go first; older photos follow.
  std::vector<uint32_t> orderedHandles;
  orderedHandles.reserve(handles.size());
  for (uint32_t handle : handles) {
    if (isNewHandle(handle) && !handledContains(handle))
      orderedHandles.push_back(handle);
  }
  for (uint32_t handle : handles) {
    if (!isNewHandle(handle) && !handledContains(handle))
      orderedHandles.push_back(handle);
  }
  // Give each new capture a small prefix before any one NEF consumes a full
  // minute. Keep the staged batch inside the current API checkpoint.
  std::vector<uint32_t> previewHandles;
  const size_t used = sessionObjectCount + gStagedHandles.size();
  const size_t available = used < MAX_SESSION_OBJECTS ?
    MAX_SESSION_OBJECTS - used : 0;
  for (uint32_t handle : orderedHandles) {
    if (!isNewHandle(handle) || previewHandles.size() >= available) break;
    previewHandles.push_back(handle);
  }
  if (previewHandles.size() < 2) previewHandles.clear();
  size_t newPhotos = 0;
  size_t imported = 0;
  size_t skipped = 0;
  size_t warnings = 0;
  bool infrastructureFailure = false;
  bool stopScan = false;
  bool pausedThisScan = false;

  // Round 1: first MB of each burst shot. Round 2: enough bytes for most NEF
  // embedded JPEGs. Round 3: resume every upload and verify the whole file.
  for (uint8_t phase = previewHandles.empty() ? 2 : 0;
       phase < 3 && !stopScan && !gDeviceGone; ++phase) {
    const std::vector<uint32_t> &phaseHandles =
      phase == 2 ? orderedHandles : previewHandles;
    const uint32_t stageBytes = phase == 0 ? BURST_FIRST_BYTES :
      (phase == 1 ? BURST_PREVIEW_BYTES : 0);
    for (uint32_t handle : phaseHandles) {
      if (gDeviceGone || stopScan) break;
      if (handledContains(handle)) continue;

      ObjectInfo object;
      if (!getObjectInfo(handle, object)) {
        Serial.printf("[SCAN] ObjectInfo failed for 0x%08lX.\n",
                      static_cast<unsigned long>(handle));
        ++warnings;
        continue;
      }
      // A camera may expose a handle before the image has finished writing.
      if (object.size == 0 && object.format != PTP_FORMAT_ASSOCIATION) {
        ++warnings;
        continue;
      }
      if (!isPhoto(object)) {
        markHandled(handle);
        continue;
      }
      if (phase == 0 ||
          (phase == 2 && std::find(previewHandles.begin(),
                                   previewHandles.end(), handle) ==
                           previewHandles.end())) {
        ++newPhotos;
        Serial.printf("[PHOTO] %s, %lu bytes, handle 0x%08lX.\n",
                      object.filename.c_str(),
                      static_cast<unsigned long>(object.size),
                      static_cast<unsigned long>(handle));
      }

      // Validate Wi-Fi/API once before reading up to three 64 KiB samples.
      // If the backend is offline or authentication is wrong, stop this scan
      // immediately instead of hashing every photo on a large card.
      if (!apiSessionId.length() &&
          !createApiSession(camera, apiSessionId)) {
        infrastructureFailure = true;
        stopScan = true;
        break;
      }

      String quickHash;
      if (!quickFingerprint(object, quickHash)) {
        ++warnings;
        continue;
      }
      Serial.printf("[HASH] quick SHA-256 %s.\n", quickHash.c_str());

      PreflightResult preflight;
      if (!preflightObject(apiSessionId, camera, object,
                           quickHash, preflight)) {
        infrastructureFailure = true;
        stopScan = true;
        break;
      }
      sessionHasObjects = true;
      if (preflight.skip) {
        markHandled(handle);
        if (handle == gPausedHandle) gPausedHandle = 0;
        ++skipped;
      } else {
        const UploadResult result =
          uploadObject(object, preflight, orderedHandles, stageBytes);
        if (result == UploadResult::Complete) {
          markHandled(handle);
          if (handle == gPausedHandle) gPausedHandle = 0;
          ++imported;
        } else if (result == UploadResult::Staged) {
          if (std::find(gStagedHandles.begin(), gStagedHandles.end(), handle) ==
              gStagedHandles.end()) gStagedHandles.push_back(handle);
          Serial.printf("[BURST] %s staged for the next round.\n",
                        object.filename.c_str());
          continue;
        } else {
          // An incomplete upload keeps the API session open. On a planned
          // pause, immediately rescan and serve the new capture first.
          if (std::find(gStagedHandles.begin(), gStagedHandles.end(), handle) ==
              gStagedHandles.end()) gStagedHandles.push_back(handle);
          pausedThisScan = result == UploadResult::Paused;
          if (pausedThisScan) {
            gPausedHandle = handle;
            gForceRescan = true;
          } else {
            infrastructureFailure = true;
          }
          stopScan = true;
          break;
        }
      }

      ++sessionObjectCount;
      if (!gPausedHandle && gStagedHandles.empty() &&
          sessionObjectCount >= MAX_SESSION_OBJECTS) {
        Serial.printf("[API] Publishing checkpoint batch (%u objects).\n",
                      static_cast<unsigned>(sessionObjectCount));
        if (!completeApiSession(apiSessionId)) {
          infrastructureFailure = true;
          stopScan = true;
          break;
        }
        apiSessionId = "";
        sessionHasObjects = false;
        sessionObjectCount = 0;
      }
    }
  }

  Serial.printf("[SCAN] New %u, uploaded %u, skipped %u, warnings %u.\n",
                static_cast<unsigned>(newPhotos),
                static_cast<unsigned>(imported),
                static_cast<unsigned>(skipped),
                static_cast<unsigned>(warnings));

  // Metadata/quick-hash warnings happened before preflight and therefore do
  // not belong to this API session. Publish verified objects now; the warning
  // handles remain unmarked and will be retried in the next scan.
  if (!gDeviceGone && !infrastructureFailure && !pausedThisScan &&
      !gPausedHandle && gStagedHandles.empty() &&
      apiSessionId.length() && sessionHasObjects) {
    if (completeApiSession(apiSessionId)) {
      apiSessionId = "";
      sessionHasObjects = false;
      sessionObjectCount = 0;
    } else {
      return false;
    }
  }
  return !infrastructureFailure;
}

static bool runCameraBridge() {
  gBulkReader.reset();
  gNextTransaction = 1;
  gHandledHandles.clear();
  gInitialHandles.clear();
  gStagedHandles.clear();
  gInitialHandlesReady = false;
  gPausedHandle = 0;

  const uint32_t sessionParameter = 1;
  if (!commandWithoutData(PTP_OC_OPEN_SESSION, 0,
                          &sessionParameter, 1)) {
    Serial.println(F("[PTP] Cannot open session."));
    return false;
  }
  Serial.println(F("[PTP] Session opened."));

  CameraIdentity camera;
  std::vector<uint8_t> payload;
  if (!commandWithData(PTP_OC_GET_DEVICE_INFO, gNextTransaction++,
                       nullptr, 0, payload, MAX_METADATA_BYTES) ||
      !parseDeviceInfo(payload, camera)) {
    return false;
  }
  if (!camera.supportsPartialObject) {
    Serial.println(F("[PTP] Safe chunk transfer is unavailable; stopping."));
    return false;
  }

  String apiSessionId;
  bool sessionHasObjects = false;
  size_t sessionObjectCount = 0;
  gForceRescan = true;
  while (!gDeviceGone) {
    if (gForceRescan) {
      gForceRescan = false;
      scanCamera(camera, apiSessionId,
                 sessionHasObjects, sessionObjectCount);
    }
    const uint32_t waitStarted = millis();
    while (!gDeviceGone && !gForceRescan &&
           millis() - waitStarted < SCAN_INTERVAL_MS) {
      delay(100);
    }
    if (!gDeviceGone) gForceRescan = true;
  }

  if (!gDeviceGone) {
    commandWithoutData(PTP_OC_CLOSE_SESSION, gNextTransaction++,
                       nullptr, 0);
  }
  return true;
}

static void cleanupDevice() {
  if (gDevice == nullptr) return;
  if (gInterfaceClaimed) {
    usb_host_interface_release(gClient, gDevice, gInterfaceNumber);
    gInterfaceClaimed = false;
  }
  const esp_err_t result = usb_host_device_close(gClient, gDevice);
  if (result != ESP_OK) {
    Serial.printf("[USB] Device close: %s.\n", esp_err_to_name(result));
  }
  gDevice = nullptr;
}

static void ptpWorkerTask(void *argument) {
  (void)argument;
  gWorkerTask = xTaskGetCurrentTaskHandle();

  while (true) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (gPendingDeviceAddress < 0 || gWorkerBusy) {
      if (gDeviceGone && !gWorkerBusy) {
        gDeviceGone = false;
        cleanupDevice();
      }
      continue;
    }

    const uint8_t address =
      static_cast<uint8_t>(gPendingDeviceAddress);
    gPendingDeviceAddress = -1;
    gDeviceGone = false;
    gWorkerBusy = true;
    Serial.printf("[USB] Opening device address %u...\n", address);

    esp_err_t result =
      usb_host_device_open(gClient, address, &gDevice);
    if (result != ESP_OK) {
      Serial.printf("[USB] Device open: %s.\n", esp_err_to_name(result));
      gDevice = nullptr;
      gWorkerBusy = false;
      continue;
    }

    const usb_device_desc_t *descriptor = nullptr;
    result = usb_host_get_device_descriptor(gDevice, &descriptor);
    if (result == ESP_OK && descriptor != nullptr) {
      Serial.printf("[USB] VID:PID %04X:%04X.\n",
                    descriptor->idVendor, descriptor->idProduct);
    }
    if (!findPtpInterface()) {
      Serial.println(F("[USB] Device is not a PTP camera."));
      cleanupDevice();
      gWorkerBusy = false;
      continue;
    }
    result = usb_host_interface_claim(gClient, gDevice,
                                      gInterfaceNumber,
                                      gAlternateSetting);
    if (result != ESP_OK) {
      Serial.printf("[USB] Interface claim: %s.\n", esp_err_to_name(result));
      cleanupDevice();
      gWorkerBusy = false;
      continue;
    }
    gInterfaceClaimed = true;
    Serial.println(F("[NIWA] Nikon connected; automatic bridge starting."));
    runCameraBridge();
    Serial.println(F("[NIWA] Camera bridge stopped."));
    cleanupDevice();
    gDeviceGone = false;
    gWorkerBusy = false;
  }
}

static void clientEventCallback(const usb_host_client_event_msg_t *event,
                                void *argument) {
  (void)argument;
  if (event->event == USB_HOST_CLIENT_EVENT_NEW_DEV) {
    gPendingDeviceAddress = event->new_dev.address;
    if (gWorkerTask != nullptr) xTaskNotifyGive(gWorkerTask);
  } else if (event->event == USB_HOST_CLIENT_EVENT_DEV_GONE) {
    gDeviceGone = true;
    if (gWorkerTask != nullptr) xTaskNotifyGive(gWorkerTask);
  }
}

static bool allowUsbEnumeration(const usb_device_desc_t *descriptor,
                                uint8_t *configurationValue) {
  (void)descriptor;
  // Arduino-ESP32 3.3.11 enables the IDF enum filter. A null callback rejects
  // every device silently. Keep the first configuration used by this bridge.
  *configurationValue = 1;
  return true;
}

static void hostLibraryTask(void *argument) {
  (void)argument;
  while (true) {
    uint32_t flags = 0;
    const esp_err_t result =
      usb_host_lib_handle_events(portMAX_DELAY, &flags);
    if (result != ESP_OK) {
      Serial.printf("[USB] Library event: %s.\n", esp_err_to_name(result));
      delay(100);
    }
  }
}

static void hostClientTask(void *argument) {
  (void)argument;
  usb_host_client_config_t configuration = {};
  configuration.is_synchronous = false;
  configuration.max_num_event_msg = 8;
  configuration.async.client_event_callback = clientEventCallback;
  configuration.async.callback_arg = nullptr;
  const esp_err_t result =
    usb_host_client_register(&configuration, &gClient);
  if (result != ESP_OK) {
    Serial.printf("[USB] Client register: %s.\n", esp_err_to_name(result));
    vTaskDelete(nullptr);
    return;
  }
  Serial.println(F("[USB] Client registered."));
  delay(400);
  const esp_err_t powerResult =
    usb_host_lib_set_root_port_power(true);
  Serial.printf("[USB] Root port power: %s.\n",
                esp_err_to_name(powerResult));
  Serial.println(F("[USB] READY - connect the powered-on Nikon."));

  while (true) {
    const esp_err_t eventResult =
      usb_host_client_handle_events(gClient, portMAX_DELAY);
    if (eventResult != ESP_OK) {
      Serial.printf("[USB] Client event: %s.\n",
                    esp_err_to_name(eventResult));
      delay(100);
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  gConfigMutex = xSemaphoreCreateMutex();
  if (gConfigMutex == nullptr) {
    Serial.println(F("[FATAL] Cannot create config mutex."));
    return;
  }
  loadConfig();
  gSerialLine.reserve(256);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.onEvent(onWiFiEvent);
  esp_log_level_set("*", ESP_LOG_INFO);

  Serial.println();
  Serial.println(F("============================================"));
  Serial.println(F(" NIWA Z6 II USB -> WI-FI BRIDGE"));
  Serial.println(F(" ESP32-S3 N16R8 / HW-678"));
  Serial.println(F("============================================"));
  Serial.println(F("Camera files are read-only; nothing is deleted."));
  Serial.println(F("Send STATUS or HELP at 115200 baud."));
  Serial.printf("[NIWA] Firmware %s; Arduino-ESP32 %s; ESP-IDF %s.\n",
                FIRMWARE_VERSION, ESP_ARDUINO_VERSION_STR, ESP.getSdkVersion());

  usb_host_config_t configuration = {};
  configuration.skip_phy_setup = false;
  configuration.root_port_unpowered = true;
  configuration.intr_flags = ESP_INTR_FLAG_LEVEL1;
  configuration.enum_filter_cb = allowUsbEnumeration;
  const esp_err_t result = usb_host_install(&configuration);
  if (result != ESP_OK) {
    Serial.printf("[USB] Host install: %s.\n", esp_err_to_name(result));
    return;
  }

  Serial.println(F("[USB] Allow-all enumeration filter installed."));
  gChunkQueue = xQueueCreate(1, sizeof(ChunkSend *));
  gChunkDone = xSemaphoreCreateBinary();
  gPipelineReady =
    gChunkQueue != nullptr && gChunkDone != nullptr &&
    xTaskCreatePinnedToCore(chunkSenderTask, "niwa_chunk_sender", 12288,
                            nullptr, 3, nullptr, tskNO_AFFINITY) == pdPASS;
  Serial.printf("[UPLOAD] Parallel camera read and Wi-Fi send: %s.\n",
                gPipelineReady ? "OK" : "OFF, sequential");
  BaseType_t created = xTaskCreatePinnedToCore(
    hostLibraryTask, "niwa_usb_library", 4096,
    nullptr, 4, nullptr, 0
  );
  Serial.printf("[USB] Library task: %s.\n",
                created == pdPASS ? "OK" : "FAILED");
  created = xTaskCreatePinnedToCore(
    ptpWorkerTask, "niwa_ptp_worker", 16384,
    nullptr, 3, nullptr, 1
  );
  Serial.printf("[USB] PTP worker: %s.\n",
                created == pdPASS ? "OK" : "FAILED");
  created = xTaskCreatePinnedToCore(
    hostClientTask, "niwa_usb_client", 6144,
    nullptr, 5, nullptr, 0
  );
  Serial.printf("[USB] Client task: %s.\n",
                created == pdPASS ? "OK" : "FAILED");
}

void loop() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (gSerialLine.length()) {
        processSerialCommand(gSerialLine);
        gSerialLine = "";
      }
    } else if (gSerialLine.length() < 512) {
      gSerialLine += c;
    }
  }
  delay(10);
}
