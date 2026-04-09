# Arduino R4 WiFi Sensor Setup Guide

## Overview
This guide explains how to set up the SMOKi sensor system on Arduino R4 WiFi, adapted from the original ESP32 version with LittleFS-like file recovery functionality using SD card storage.

## Key Differences from ESP32 Version

### Hardware Differences
- **WiFi Library**: Uses `WiFiS3.h` instead of `WiFi.h`
- **HTTP Client**: Uses `ArduinoHttpClient.h` instead of `HTTPClient.h`
- **File Storage**: Uses SD card instead of LittleFS
- **Serial Ports**: Uses `Serial1` for PMS7003 communication
- **Pin Assignments**: Adapted for Arduino R4 WiFi pinout

### Software Adaptations
- **Offline Storage**: SD card replaces LittleFS functionality
- **File Recovery**: Similar logic but using SD card file operations
- **SSL/HTTPS**: Uses `WiFiSSLClient` for secure connections
- **Memory Management**: Optimized for Arduino R4 WiFi memory constraints

## Hardware Requirements

### Core Components
- Arduino R4 WiFi board
- MicroSD card (8GB or larger, Class 10 recommended)
- MicroSD card module or shield

### Sensors
- **BME680**: Temperature, humidity, pressure, VOC sensor
- **ADS1115**: 16-bit ADC for analog sensors
- **MICS6814**: Gas sensor (NO2, CO, NH3)
- **PMS7003**: Particulate matter sensor (PM2.5, PM10)

### Connections

#### BME680 (SPI)
```
BME680    Arduino R4 WiFi
VCC   →   3.3V
GND   →   GND
SCK   →   13 (SCK)
MISO  →   12 (MISO)
MOSI  →   11 (MOSI)
CS    →   10 (BME_CS)
```

#### ADS1115 (I2C)
```
ADS1115   Arduino R4 WiFi
VCC   →   3.3V
GND   →   GND
SCL   →   A5 (SCL)
SDA   →   A4 (SDA)
```

#### MICS6814 → ADS1115
```
MICS6814  ADS1115
RED   →   A0 (Channel 0)
OX    →   A1 (Channel 1)
NH3   →   A2 (Channel 2)
```

#### PMS7003 (UART)
```
PMS7003   Arduino R4 WiFi
VCC   →   5V
GND   →   GND
TX    →   0 (Serial1 RX)
RX    →   1 (Serial1 TX)
```

#### SD Card Module
```
SD Module Arduino R4 WiFi
VCC   →   3.3V
GND   →   GND
MISO  →   12 (shared with BME680)
MOSI  →   11 (shared with BME680)
SCK   →   13 (shared with BME680)
CS    →   4 (SD_CS)
```

## Software Setup

### Required Libraries
Install these libraries through Arduino IDE Library Manager:

```
1. WiFiS3 (built-in for Arduino R4 WiFi)
2. ArduinoHttpClient
3. ArduinoJson
4. SD (built-in)
5. Wire (built-in)
6. SPI (built-in)
7. Adafruit Sensor
8. Adafruit BME680 Library
9. Adafruit ADS1X15
```

### Installation Steps

1. **Install Arduino IDE** (version 2.0 or later)
2. **Add Arduino R4 WiFi board support**:
   - Go to Tools → Board → Boards Manager
   - Search for "Arduino UNO R4 WiFi"
   - Install the board package

3. **Install required libraries** (listed above)

4. **Prepare SD card**:
   - Format as FAT32
   - Insert into SD card module

5. **Upload the code**:
   - Open `arduino_r4_sensor_sender.ino`
   - Configure WiFi credentials
   - Select "Arduino UNO R4 WiFi" as board
   - Upload to your Arduino

## Configuration

### WiFi Settings
```cpp
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
```

### API Endpoint
```cpp
const char* server = "smoki-backend-rpi.onrender.com";
const char* api_path = "/api/sensors/data";
```

### Device ID
```cpp
const char* device_id = "arduino_r4_living_room";
```

## File Recovery System

### How It Works
The Arduino R4 version implements LittleFS-like functionality using SD card storage:

1. **Online Mode**: Data is sent directly to the API
2. **Offline Mode**: Data is stored in `offline.txt` on SD card
3. **Recovery**: When WiFi reconnects, stored data is automatically sent
4. **Cleanup**: Successfully sent offline data is removed from storage

### File Structure
```
SD Card Root/
├── offline.txt (JSON records, one per line)
```

### Recovery Process
1. WiFi connection restored
2. Read `offline.txt` line by line
3. Send each JSON record to API
4. On success, clear the offline file
5. On failure, preserve remaining data

## Monitoring and Debugging

### Serial Output
The system provides detailed logging via Serial (115200 baud):

```
=== SMOKi Arduino R4 WiFi Sensor System ===
✓ SD Card initialized
✓ ADS1115 initialized
✓ BME680 initialized
✓ PMS7003 initialized on Serial1
✓ WiFi connected!
IP address: 192.168.1.100
🚀 System ready!

=== Sensor Readings ===
{"device_id":"arduino_r4_living_room","temperature":23.45,"humidity":45.67,...}
✓ Data sent successfully
========================
```

### Status Indicators
- ✓ Success operations
- ❌ Error conditions
- 🔄 Reconnection attempts
- 💾 Offline storage
- 📤 Data transmission
- 🧹 Cleanup operations

## Troubleshooting

### Common Issues

#### SD Card Problems
```
❌ SD Card initialization failed!
```
**Solutions**:
- Check SD card formatting (FAT32)
- Verify wiring connections
- Try different SD card
- Check power supply (3.3V)

#### WiFi Connection Issues
```
❌ WiFi connection failed!
```
**Solutions**:
- Verify SSID and password
- Check WiFi signal strength
- Restart Arduino
- Check antenna connection

#### Sensor Reading Errors
```
❌ Failed to read BME680
```
**Solutions**:
- Check sensor wiring
- Verify I2C/SPI connections
- Check power supply
- Test with sensor examples

#### PMS7003 No Data
```
PMS7003 data invalid
```
**Solutions**:
- Check UART connections
- Verify 5V power supply
- Clean sensor fan
- Check for loose connections

### Memory Optimization

If you encounter memory issues:

1. **Reduce JSON buffer size**:
   ```cpp
   StaticJsonDocument<256> doc; // Reduce from 512
   ```

2. **Optimize string usage**:
   ```cpp
   // Use F() macro for constant strings
   Serial.println(F("Static text"));
   ```

3. **Limit offline storage**:
   ```cpp
   // Add file size check before writing
   if (file.size() > 10000) { // 10KB limit
     // Clear old data or skip saving
   }
   ```

## Performance Characteristics

### Timing
- **Sensor Reading**: Every 5 seconds
- **PMS7003 Continuous**: Real-time parsing
- **WiFi Retry**: 10 attempts with 500ms intervals
- **Offline Flush**: Automatic on reconnection

### Memory Usage
- **RAM**: ~60% of Arduino R4 WiFi (32KB)
- **Flash**: ~40% of Arduino R4 WiFi (256KB)
- **SD Storage**: Limited by card size

### Power Consumption
- **Active**: ~200-300mA (depending on sensors)
- **WiFi Transmit**: Peak ~400mA
- **Idle**: ~150mA

## Advanced Features

### Custom Calibration
Modify sensor conversion formulas in `readMICS6814()`:
```cpp
// Calibrated conversion factors
co  = (red_v - baseline_co) * calibration_factor_co;
no2 = (ox_v - baseline_no2) * calibration_factor_no2;
```

### Data Validation
Add sensor range checking:
```cpp
if (temp < -40 || temp > 85) {
  Serial.println("❌ Temperature out of range");
  return false;
}
```

### Watchdog Timer
For production deployment, consider adding watchdog functionality:
```cpp
#include <avr/wdt.h>

void setup() {
  wdt_enable(WDTO_8S); // 8 second watchdog
}

void loop() {
  wdt_reset(); // Reset watchdog
  // ... your code ...
}
```

## Comparison with ESP32 Version

| Feature | ESP32 | Arduino R4 WiFi |
|---------|-------|-----------------|
| WiFi Library | WiFi.h | WiFiS3.h |
| HTTP Client | HTTPClient | ArduinoHttpClient |
| File System | LittleFS | SD Card |
| Flash Memory | 4MB | 256KB |
| RAM | 520KB | 32KB |
| CPU Speed | 240MHz | 48MHz |
| Power Usage | Higher | Lower |
| Cost | Lower | Higher |

## Production Deployment

### Enclosure Requirements
- IP65 rated for outdoor use
- Ventilation for sensors
- SD card access port
- Status LED visibility

### Power Supply
- 5V 2A minimum
- Consider UPS for continuous operation
- Solar panel option for remote locations

### Maintenance
- Monthly SD card check
- Quarterly sensor cleaning
- Annual calibration verification

This Arduino R4 WiFi version provides equivalent functionality to the ESP32 version while adapting to the different hardware platform and using SD card storage for offline data recovery.