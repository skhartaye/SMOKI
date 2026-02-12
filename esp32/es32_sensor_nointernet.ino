#include <SPI.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME680.h>
#include <Adafruit_ADS1X15.h>

// ================= BME680 (SPI) =================
#define BME_CS 5
Adafruit_BME680 bme(BME_CS);

// ================= PMS7003 =================
#define PMS7003_RX 17
#define PMS7003_TX 16
HardwareSerial pmsSerial(1);

// ================= ADS1115 =================
Adafruit_ADS1115 ads;

// MiCS-6814 channels
#define MICS_RED_CH   0   // CO
#define MICS_OX_CH    1   // NO2
#define MICS_NH3_CH   2   // NH3

// ================= TIMING =================
unsigned long lastADSRead = 0;

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(1000);

  // I2C for ADS1115
  Wire.begin(21, 22);

  if (!ads.begin()) {
    Serial.println("❌ ADS1115 not found!");
    while (1);
  }

  ads.setGain(GAIN_ONE); // ±4.096V (safe for 3.3V systems)

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

  // PMS7003
  pmsSerial.begin(9600, SERIAL_8N1, PMS7003_RX, PMS7003_TX);

  Serial.println("✅ PMS7003 + BME680 + MiCS-6814 initialized");
}

// ================= LOOP =================
void loop() {

  // ---------- BME680 ----------
  if (bme.performReading()) {
    Serial.print("BME680 -> T:");
    Serial.print(bme.temperature);
    Serial.print("C H:");
    Serial.print(bme.humidity);
    Serial.print("% Gas:");
    Serial.print(bme.gas_resistance / 1000.0);
    Serial.println("kΩ");
  }

  // ---------- PMS7003 (KEEP THIS STYLE) ----------
  byte buffer[32];
  int count = 0;

  while (pmsSerial.available()) {
    byte data = pmsSerial.read();
    if (count < 32) buffer[count++] = data;
  }

  if (count == 32 && buffer[0] == 0x42 && buffer[1] == 0x4D) {
    uint16_t pm1_0 = (buffer[10] << 8) | buffer[11];
    uint16_t pm2_5 = (buffer[12] << 8) | buffer[13];
    uint16_t pm10  = (buffer[14] << 8) | buffer[15];


    Serial.print("PM1.0:");
    Serial.print(pm1_0);
    Serial.print(" PM2.5:");
    Serial.print(pm2_5);
    Serial.print(" PM10:");
    Serial.println(pm10);
  }

  // ---------- MiCS-6814 via ADS1115 ----------
  if (millis() - lastADSRead >= 3000) {
    lastADSRead = millis();

    int16_t red_raw  = ads.readADC_SingleEnded(MICS_RED_CH);
    int16_t ox_raw   = ads.readADC_SingleEnded(MICS_OX_CH);
    int16_t nh3_raw  = ads.readADC_SingleEnded(MICS_NH3_CH);

    float red_v  = red_raw * 0.125 / 1000.0; // ADS1115 GAIN_ONE
    float ox_v   = ox_raw  * 0.125 / 1000.0;
    float nh3_v  = nh3_raw * 0.125 / 1000.0;

    Serial.print("MiCS -> CO:");
    Serial.print(red_v, 3);
    Serial.print("V NO2:");
    Serial.print(ox_v, 3);
    Serial.print("V NH3:");
    Serial.print(nh3_v, 3);
    Serial.println("V");
  }

  Serial.println("-----");
  delay(2000); // Keep your known-good timing
}