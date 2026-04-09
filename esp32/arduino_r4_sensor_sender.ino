/**
 * Arduino R4 WiFi Sensor Data Sender for SMOKi Project
 * Sensors: BME680, MICS6814, PMS7003
 * Features:
 *  - Continuous PMS7003 reading
 *  - Offline storage using SD card (similar to LittleFS)
 *  - Auto resend when WiFi reconnects
 *  - Compatible with Arduino R4 WiFi
 */

#include <WiFiS3.h>
#include <ArduinoHttpClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <Wire.h>
#include <SD.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <Adafruit_ADS1X15.h>

// ============ CONFIGURATION ============
const char* ssid = "SMOKi";
const char* password = "smoki1234";
const char* server = "smoki-backend-rpi.onrender.com";
const int port = 443; // HTTPS
const char* api_path = "/api/sensors/data";
const char* device_id = "arduino_r4_living_room";

// Pin definitions for Arduino R4 WiFi
#define BME_CS 10
#define SD_CS 4
#define PMS7003_RX 0  // Use Serial1 RX
#define PMS7003_TX 1  // Use Serial1 TX

// ADS1115 channels
#define MICS_RED_CH   0
#define MICS_OX_CH    1
#define MICS_NH3_CH   2

// Timing
const long postInterval = 5000;
const char* offlineFile = "offline.txt";

// ============ OBJECTS ============
Adafruit_BME680 bme(BME_CS);
Adafruit_ADS1115 ads;
WiFiSSLClient wifiClient;
HttpClient httpClient = HttpClient(wifiClient, server, port);
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
  delay(2000);
  
  Serial.println("\n=== SMOKi Arduino R4 WiFi Sensor System ===");
  
  // Initialize SD card for offline storage
  if (!SD.begin(SD_CS)) {
    Serial.println("❌ SD Card initialization failed!");
    Serial.println("⚠️  Continuing without offline storage...");
  } else {
    Serial.println("✓ SD Card initialized");
    
    // Create offline file if it doesn't exist
    if (!SD.exists(offlineFile)) {
      File file = SD.open(offlineFile, FILE_WRITE);
      if (file) {
        file.close();
        Serial.println("✓ Offline storage file created");
      }
    }
  }
  
  // I2C initialization
  Wire.begin();
  
  // ADS1115 initialization
  if (!ads.begin()) {
    Serial.println("❌ ADS1115 not found!");
    while (1) {
      delay(1000);
      Serial.println("Retrying ADS1115...");
    }
  }
  ads.setGain(GAIN_ONE);
  Serial.println("✓ ADS1115 initialized");
  
  // BME680 initialization
  if (!bme.begin()) {
    Serial.println("❌ BME680 not found!");
    while (1) {
      delay(1000);
      Serial.println("Retrying BME680...");
    }
  }
  
  // Configure BME680
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);
  Serial.println("✓ BME680 initialized");
  
  // PMS7003 initialization using Serial1
  Serial1.begin(9600);
  Serial.println("✓ PMS7003 initialized on Serial1");
  
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
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    
    // Try to flush offline data when connected
    flushOfflineData();
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

// ============ SD CARD STORAGE (LittleFS-like functionality) ============
void saveOfflineData(const char* json) {
  if (!SD.begin(SD_CS)) {
    Serial.println("❌ SD card not available for offline storage");
    return;
  }
  
  File file = SD.open(offlineFile, FILE_WRITE);
  if (!file) {
    Serial.println("❌ Failed to open offline file for writing");
    return;
  }
  
  file.println(json);
  file.close();
  Serial.println("💾 Data saved offline to SD card");
}

void flushOfflineData() {
  if (!SD.begin(SD_CS)) {
    Serial.println("❌ SD card not available for reading offline data");
    return;
  }
  
  if (!SD.exists(offlineFile)) {
    Serial.println("📁 No offline data to flush");
    return;
  }
  
  File file = SD.open(offlineFile, FILE_READ);
  if (!file) {
    Serial.println("❌ Failed to read offline file");
    return;
  }
  
  Serial.println("📤 Sending stored offline data...");
  
  // Read all offline data into memory first
  String allData = "";
  while (file.available()) {
    allData += file.readString();
  }
  file.close();
  
  if (allData.length() == 0) {
    Serial.println("📁 Offline file is empty");
    return;
  }
  
  // Process each line
  int startIndex = 0;
  int endIndex = 0;
  int successCount = 0;
  
  while (endIndex != -1) {
    endIndex = allData.indexOf('\n', startIndex);
    String line;
    
    if (endIndex == -1) {
      line = allData.substring(startIndex);
    } else {
      line = allData.substring(startIndex, endIndex);
    }
    
    line.trim();
    if (line.length() == 0) {
      startIndex = endIndex + 1;
      continue;
    }
    
    // Send the offline record
    httpClient.beginRequest();
    httpClient.post(api_path);
    httpClient.sendHeader("Content-Type", "application/json");
    httpClient.sendHeader("Content-Length", line.length());
    httpClient.beginBody();
    httpClient.print(line);
    httpClient.endRequest();
    
    int statusCode = httpClient.responseStatusCode();
    String response = httpClient.responseBody();
    
    if (statusCode == 200) {
      Serial.println("✓ Offline record sent successfully");
      successCount++;
    } else {
      Serial.print("❌ Failed sending offline record. Status: ");
      Serial.println(statusCode);
      break; // Stop processing if we fail
    }
    
    startIndex = endIndex + 1;
    delay(100); // Small delay between requests
  }
  
  // If all records were sent successfully, clear the offline file
  if (successCount > 0) {
    SD.remove(offlineFile);
    // Recreate empty file
    File newFile = SD.open(offlineFile, FILE_WRITE);
    if (newFile) {
      newFile.close();
    }
    Serial.print("🧹 Offline storage cleared. Sent ");
    Serial.print(successCount);
    Serial.println(" records.");
  }
}

// ============ PMS7003 ============
void readPMS7003Continuous() {
  static byte buffer[32];
  static int count = 0;
  static unsigned long lastByte = 0;
  
  // Reset buffer if no data received for 2 seconds
  if (millis() - lastByte > 2000 && count > 0) {
    count = 0;
  }
  
  // Read available data from Serial1
  while (Serial1.available()) {
    byte data = Serial1.read();
    lastByte = millis();
    if (count < 32) buffer[count++] = data;
  }
  
  // Process complete frame
  if (count == 32 && buffer[0] == 0x42 && buffer[1] == 0x4D) {
    // Calculate checksum
    uint16_t checksum = 0;
    for (int i = 0; i < 30; i++) {
      checksum += buffer[i];
    }
    uint16_t receivedChecksum = (buffer[30] << 8) | buffer[31];
    
    if (checksum == receivedChecksum) {
      pmsData.pm25 = (buffer[12] << 8) | buffer[13];
      pmsData.pm10 = (buffer[14] << 8) | buffer[15];
      pmsData.valid = true;
      pmsData.lastUpdate = millis();
      
      Serial.print("PMS7003: PM2.5=");
      Serial.print(pmsData.pm25);
      Serial.print(" PM10=");
      Serial.println(pmsData.pm10);
    } else {
      Serial.println("❌ PMS7003 checksum error");
    }
    
    count = 0;
  }
  
  // Mark data as invalid if too old
  if (millis() - pmsData.lastUpdate > 30000) {
    pmsData.valid = false;
  }
}

// ============ SENSORS ============
bool readBME680(float &temp, float &humidity, float &pressure, float &voc) {
  if (!bme.performReading()) {
    Serial.println("❌ Failed to perform BME680 reading");
    return false;
  }
  
  temp = bme.temperature;
  humidity = bme.humidity;
  pressure = bme.pressure / 100.0; // Convert Pa to hPa
  voc = bme.gas_resistance / 1000.0; // Convert to kOhms
  
  return true;
}

void readMICS6814(float &no2, float &co, float &nh3) {
  int16_t red_raw  = ads.readADC_SingleEnded(MICS_RED_CH);
  int16_t ox_raw   = ads.readADC_SingleEnded(MICS_OX_CH);
  int16_t nh3_raw  = ads.readADC_SingleEnded(MICS_NH3_CH);
  
  // Convert to voltage (ADS1115 with GAIN_ONE: 1 bit = 0.125mV)
  float red_v  = red_raw * 0.125 / 1000.0;
  float ox_v   = ox_raw  * 0.125 / 1000.0;
  float nh3_v  = nh3_raw * 0.125 / 1000.0;
  
  // Simple conversion (adjust based on your calibration)
  co  = red_v * 100.0;  // CO in ppm
  no2 = ox_v * 100.0;   // NO2 in ppm
  nh3 = nh3_v * 100.0;  // NH3 in ppm
}

// ============ POST ============
void postSensorData() {
  float temp, humidity, pressure, voc;
  float no2, co, nh3;
  
  // Read BME680
  if (!readBME680(temp, humidity, pressure, voc)) {
    Serial.println("❌ Failed to read BME680, skipping this cycle");
    return;
  }
  
  // Read MICS6814
  readMICS6814(no2, co, nh3);
  
  // Create JSON payload
  StaticJsonDocument<512> doc;
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
  
  char jsonBuffer[512];
  serializeJson(doc, jsonBuffer);
  
  Serial.println("=== Sensor Readings ===");
  Serial.println(jsonBuffer);
  
  // Ensure WiFi connection
  ensureWiFi();
  
  if (WiFi.status() == WL_CONNECTED) {
    // Send data via HTTPS
    httpClient.beginRequest();
    httpClient.post(api_path);
    httpClient.sendHeader("Content-Type", "application/json");
    httpClient.sendHeader("Content-Length", strlen(jsonBuffer));
    httpClient.beginBody();
    httpClient.print(jsonBuffer);
    httpClient.endRequest();
    
    int statusCode = httpClient.responseStatusCode();
    String response = httpClient.responseBody();
    
    if (statusCode == 200) {
      Serial.println("✓ Data sent successfully");
    } else {
      Serial.print("❌ POST failed with status: ");
      Serial.print(statusCode);
      Serial.println(" → saving offline");
      saveOfflineData(jsonBuffer);
    }
  } else {
    Serial.println("📡 No WiFi → saving offline");
    saveOfflineData(jsonBuffer);
  }
  
  Serial.println("========================\n");
}