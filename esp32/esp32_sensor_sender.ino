/**
 * ESP32 Sensor Data Sender for SMOKi Project
 * Sensors: BME680, MICS6814, PMS7003
 * Features:
 *  - Continuous PMS7003 reading
 *  - Offline storage using LittleFS
 *  - Auto resend when WiFi reconnects
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <Wire.h>
#include <LittleFS.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <Adafruit_ADS1X15.h>

// ============ CONFIGURATION ============
const char* ssid = "SMOKi";
const char* password = "smoki1234";
const char* api_url = "https://smoki-backend.onrender.com/api/sensors/data";
const char* device_id = "esp32_living_room";

// BME680 SPI
#define BME_CS 5

// PMS7003 UART
#define PMS7003_RX 17
#define PMS7003_TX 16

// ADS1115 channels
#define MICS_RED_CH   0
#define MICS_OX_CH    1
#define MICS_NH3_CH   2

// Timing
const long postInterval = 5000;

// ============ OBJECTS ============
Adafruit_BME680 bme(BME_CS);
Adafruit_ADS1115 ads;
HardwareSerial pmsSerial(1);
WiFiClientSecure wifiClient;
HTTPClient http;
unsigned long lastPost = 0;

// PMS7003 storage
struct PMSData {
  float pm25 = 0;
  float pm10 = 0;
  bool valid = false;
  unsigned long lastUpdate = 0;
} pmsData;

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n=== SMOKi ESP32 Sensor System ===");
  
  // LittleFS
  if (!LittleFS.begin(true)) {
    Serial.println("❌ LittleFS Mount Failed!");
    while (1);
  }
  Serial.println("✓ LittleFS mounted");
  
  // I2C
  Wire.begin(32, 33);
  
  // ADS1115
  if (!ads.begin()) {
    Serial.println("❌ ADS1115 not found!");
    while (1);
  }
  ads.setGain(GAIN_ONE);
  Serial.println("✓ ADS1115 initialized");
  
  // BME680
  if (!bme.begin()) {
    Serial.println("❌ BME680 not found!");
    while (1);
  }
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);
  Serial.println("✓ BME680 initialized");
  
  // PMS7003
  pmsSerial.begin(9600, SERIAL_8N1, PMS7003_RX, PMS7003_TX);
  Serial.println("✓ PMS7003 initialized");
  
  wifiClient.setInsecure();
  setupWiFi();
  
  Serial.println("\n🚀 System ready!");
}

// ============ MAIN LOOP ============
void loop() {
  unsigned long now = millis();
  
  readPMS7003Continuous();
  
  if (now - lastPost >= postInterval) {
    lastPost = now;
    postSensorData();
  }
  
  delay(10);
}

// ============ WIFI ============
void setupWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi connected!");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n❌ WiFi connection failed!");
  }
}

void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  Serial.println("🔄 Reconnecting WiFi...");
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 10) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi reconnected!");
    flushOfflineData();
  } else {
    Serial.println("\n❌ WiFi still offline");
  }
}

// ============ LITTLEFS STORAGE ============
void saveOfflineData(const char* json) {
  File file = LittleFS.open("/offline.txt", FILE_APPEND);
  if (!file) {
    Serial.println("❌ Failed to open offline file");
    return;
  }
  
  file.println(json);
  file.close();
  Serial.println("💾 Data saved offline");
}

void flushOfflineData() {
  if (!LittleFS.exists("/offline.txt")) return;
  
  File file = LittleFS.open("/offline.txt", FILE_READ);
  if (!file) {
    Serial.println("❌ Failed to read offline file");
    return;
  }
  
  Serial.println("📤 Sending stored offline data...");
  
  while (file.available()) {
    String line = file.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;
    
    http.begin(wifiClient, api_url);
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(line);
    
    if (httpCode == 200) {
      Serial.println("✓ Offline record sent");
    } else {
      Serial.println("❌ Failed sending offline record");
      http.end();
      file.close();
      return;
    }
    
    http.end();
    delay(100);
  }
  
  file.close();
  LittleFS.remove("/offline.txt");
  Serial.println("🧹 Offline storage cleared");
}

// ============ PMS7003 ============
void readPMS7003Continuous() {
  static byte buffer[32];
  static int count = 0;
  static unsigned long lastByte = 0;
  
  if (millis() - lastByte > 2000 && count > 0) {
    count = 0;
  }
  
  while (pmsSerial.available()) {
    byte data = pmsSerial.read();
    lastByte = millis();
    if (count < 32) buffer[count++] = data;
  }
  
  if (count == 32 && buffer[0] == 0x42 && buffer[1] == 0x4D) {
    pmsData.pm25 = (buffer[12] << 8) | buffer[13];
    pmsData.pm10 = (buffer[14] << 8) | buffer[15];
    pmsData.valid = true;
    pmsData.lastUpdate = millis();
    count = 0;
  }
  
  if (millis() - pmsData.lastUpdate > 30000) {
    pmsData.valid = false;
  }
}

// ============ SENSORS ============
bool readBME680(float &temp, float &humidity, float &pressure, float &voc) {
  if (!bme.performReading()) return false;
  
  temp = bme.temperature;
  humidity = bme.humidity;
  pressure = bme.pressure / 100.0;
  voc = bme.gas_resistance / 1000.0;
  
  return true;
}

void readMICS6814(float &no2, float &co, float &nh3) {
  int16_t red_raw  = ads.readADC_SingleEnded(MICS_RED_CH);
  int16_t ox_raw   = ads.readADC_SingleEnded(MICS_OX_CH);
  int16_t nh3_raw  = ads.readADC_SingleEnded(MICS_NH3_CH);
  
  float red_v  = red_raw * 0.125 / 1000.0;
  float ox_v   = ox_raw  * 0.125 / 1000.0;
  float nh3_v  = nh3_raw * 0.125 / 1000.0;
  
  co  = red_v * 100.0;
  no2 = ox_v * 100.0;
  nh3 = nh3_v * 100.0;
}

// ============ POST ============
void postSensorData() {
  float temp, humidity, pressure, voc;
  float no2, co, nh3;
  
  if (!readBME680(temp, humidity, pressure, voc)) {
    Serial.println("❌ Failed to read BME680");
    return;
  }
  
  readMICS6814(no2, co, nh3);
  
  StaticJsonDocument<256> doc;
  doc["device_id"] = device_id;
  doc["temperature"] = round(temp * 100) / 100.0;
  doc["humidity"] = round(humidity * 100) / 100.0;
  doc["vocs"] = round(voc * 100) / 100.0;
  doc["nitrogen_dioxide"] = round(no2 * 1000) / 1000.0;
  doc["carbon_monoxide"] = round(co * 1000) / 1000.0;
  doc["pm25"] = pmsData.valid ? round(pmsData.pm25 * 10) / 10.0 : 0;
  doc["pm10"] = pmsData.valid ? round(pmsData.pm10 * 10) / 10.0 : 0;
  doc["pressure"] = round(pressure * 100) / 100.0;
  doc["timestamp"] = millis();
  
  char jsonBuffer[256];
  serializeJson(doc, jsonBuffer);
  
  Serial.println("=== Sensor Readings ===");
  Serial.println(jsonBuffer);
  
  ensureWiFi();
  
  if (WiFi.status() == WL_CONNECTED) {
    http.begin(wifiClient, api_url);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(15000);
    
    int httpCode = http.POST(jsonBuffer);
    
    if (httpCode == 200) {
      Serial.println("✓ Data sent successfully");
    } else {
      Serial.println("❌ POST failed → saving offline");
      saveOfflineData(jsonBuffer);
    }
    
    http.end();
  } else {
    Serial.println("📡 No WiFi → saving offline");
    saveOfflineData(jsonBuffer);
  }
  
  Serial.println("========================\n");
}
