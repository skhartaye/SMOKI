/** 
 * ESP32 Sensor Data Sender for SMOKi Project
 * Sensors: BME680, MICS6814, PMS7003
 * Fixed: Continuous PMS7003 reading to prevent data loss
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <Adafruit_ADS1X15.h>

// ============ CONFIGURATION ============
const char* ssid = "SMOKi";
const char* password = "smoki1234";

// FastAPI server settings - ONLINE BACKEND
const char* api_url = "https://smoki-backend.onrender.com/api/sensors/data";
const char* device_id = "esp32_living_room";

// BME680 SPI pins
#define BME_CS 5

// PMS7003 pins
#define PMS7003_RX 17
#define PMS7003_TX 16

// ADS1115 channels for MICS6814
#define MICS_RED_CH   0   // CO sensor
#define MICS_OX_CH    1   // NO2 sensor
#define MICS_NH3_CH   2   // NH3 sensor

// Timing
const long postInterval = 5000; // Post data every 5 seconds

// ============ OBJECTS ============
Adafruit_BME680 bme(BME_CS);
Adafruit_ADS1115 ads;
HardwareSerial pmsSerial(1);
WiFiClientSecure wifiClient;
HTTPClient http;

unsigned long lastPost = 0;

// PMS7003 data storage
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
  
  Serial.println("\n\n=== SMOKi ESP32 Sensor System ===");
  
  // Initialize I2C for ADS1115
  Wire.begin(21, 22);
  
  // Initialize ADS1115
  if (!ads.begin()) {
    Serial.println("❌ ADS1115 not found!");
    while (1) delay(100);
  }
  ads.setGain(GAIN_ONE);
  Serial.println("✓ ADS1115 initialized");
  
  // Initialize BME680 (SPI mode)
  if (!bme.begin()) {
    Serial.println("❌ BME680 not found!");
    while (1) delay(100);
  }
  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);
  bme.setGasHeater(320, 150);
  Serial.println("✓ BME680 initialized");
  
  // Initialize PMS7003
  pmsSerial.begin(9600, SERIAL_8N1, PMS7003_RX, PMS7003_TX);
  Serial.println("✓ PMS7003 initialized");
  
  // Setup WiFi client for HTTPS
  wifiClient.setInsecure(); // Skip certificate verification
  
  // Connect to WiFi
  setupWiFi();
  
  Serial.println("\n🚀 System ready! Posting data every 5 seconds...");
  Serial.printf("📡 Sending to: %s\n\n", api_url);
}

// ============ MAIN LOOP ============
void loop() {
  unsigned long now = millis();
  
  // ALWAYS read PMS7003 (non-blocking, continuous)
  readPMS7003Continuous();
  
  // Post data at intervals
  if (now - lastPost >= postInterval) {
    lastPost = now;
    postSensorData();
  }
  
  delay(10); // Small delay to prevent watchdog issues
}

// ============ WIFI SETUP ============
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
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n❌ WiFi connection failed!");
  }
}

// ============ READ PMS7003 CONTINUOUSLY ============
void readPMS7003Continuous() {
  static byte buffer[32];
  static int count = 0;
  static unsigned long lastByte = 0;
  
  // Reset buffer if no data for 2 seconds
  if (millis() - lastByte > 2000 && count > 0) {
    count = 0;
  }
  
  // Read available bytes
  while (pmsSerial.available()) {
    byte data = pmsSerial.read();
    lastByte = millis();
    
    if (count < 32) {
      buffer[count++] = data;
    }
  }
  
  // Parse complete packet
  if (count == 32 && buffer[0] == 0x42 && buffer[1] == 0x4D) {
    pmsData.pm25 = (buffer[12] << 8) | buffer[13];
    pmsData.pm10 = (buffer[14] << 8) | buffer[15];
    pmsData.valid = true;
    pmsData.lastUpdate = millis();
    
    count = 0; // Reset for next packet
  }
  
  // Mark data as stale if no update for 30 seconds
  if (millis() - pmsData.lastUpdate > 30000) {
    pmsData.valid = false;
  }
}

// ============ READ SENSORS ============
bool readBME680(float &temp, float &humidity, float &pressure, float &voc) {
  if (!bme.performReading()) return false;
  
  temp = bme.temperature;
  humidity = bme.humidity;
  pressure = bme.pressure / 100.0;
  voc = bme.gas_resistance / 1000.0;
  
  return true;
}

void readMICS6814(float &no2, float &co, float &nh3) {
  // Read raw ADC values from ADS1115
  int16_t red_raw  = ads.readADC_SingleEnded(MICS_RED_CH);
  int16_t ox_raw   = ads.readADC_SingleEnded(MICS_OX_CH);
  int16_t nh3_raw  = ads.readADC_SingleEnded(MICS_NH3_CH);
  
  // Convert to voltage
  float red_v  = red_raw * 0.125 / 1000.0;
  float ox_v   = ox_raw  * 0.125 / 1000.0;
  float nh3_v  = nh3_raw * 0.125 / 1000.0;
  
  // Convert voltage to ppm
  co = red_v * 100.0;
  no2 = ox_v * 100.0;
  nh3 = nh3_v * 100.0;
}

// ============ POST SENSOR DATA ============
void postSensorData() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️  WiFi not connected");
    return;
  }
  
  // Read sensors
  float temp, humidity, pressure, voc;
  float no2, co, nh3;
  
  if (!readBME680(temp, humidity, pressure, voc)) {
    Serial.println("❌ Failed to read BME680");
    return;
  }
  
  readMICS6814(no2, co, nh3);
  
  // Check if PM data is valid
  if (!pmsData.valid) {
    Serial.println("⚠️  Waiting for valid PM sensor data...");
  }
  
  // Create JSON in the format expected by backend
  StaticJsonDocument<256> doc;
  doc["temperature"] = round(temp * 100) / 100.0;
  doc["humidity"] = round(humidity * 100) / 100.0;
  doc["vocs"] = round(voc * 100) / 100.0;
  doc["nitrogen_dioxide"] = round(no2 * 1000) / 1000.0;
  doc["carbon_monoxide"] = round(co * 1000) / 1000.0;
  doc["pm25"] = pmsData.valid ? round(pmsData.pm25 * 10) / 10.0 : 0;
  doc["pm10"] = pmsData.valid ? round(pmsData.pm10 * 10) / 10.0 : 0;
  doc["pressure"] = round(pressure * 100) / 100.0;  // Atmospheric pressure in hPa
  
  // Serialize
  char buffer[256];
  serializeJson(doc, buffer);
  
  // Print data
  Serial.println("=== Sensor Readings ===");
  Serial.printf("🌡️  Temp: %.1f°C\n", temp);
  Serial.printf("💧 Humidity: %.1f%%\n", humidity);
  Serial.printf("🌫️  VOCs: %.1f kΩ\n", voc);
  Serial.printf("� Pressure: %.2f hPa\n", pressure);
  Serial.printf("�💨 NO2: %.3f PPM\n", no2);
  Serial.printf("🔥 CO: %.3f PPM\n", co);
  Serial.printf("⚫ PM2.5: %.1f µg/m³ %s\n", pmsData.pm25, pmsData.valid ? "✓" : "⚠️");
  Serial.printf("⚫ PM10: %.1f µg/m³ %s\n", pmsData.pm10, pmsData.valid ? "✓" : "⚠️");
  
  // POST request
  Serial.println("\n📤 Sending to server...");
  http.begin(wifiClient, api_url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(30000); // 30 second timeout for online backend
  
  int httpCode = http.POST(buffer);
  
  if (httpCode > 0) {
    Serial.printf("✓ Response: %d\n", httpCode);
    if (httpCode == HTTP_CODE_OK || httpCode == 200) {
      String response = http.getString();
      Serial.println("✓ Data saved to online database!");
      Serial.printf("Response: %s\n", response.c_str());
    }
  } else {
    Serial.printf("❌ POST failed: %s\n", http.errorToString(httpCode).c_str());
    Serial.println("💡 Backend might be sleeping (Render free tier)");
    Serial.println("   Wait 30 seconds and it will wake up");
  }
  
  http.end();
  Serial.println("========================\n");
}
