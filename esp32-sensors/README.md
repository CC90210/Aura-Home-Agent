# ESP32 Room Sensors — Phase 4

ESP32-based room sensors using ESPHome. Temperature, humidity, motion, and air quality monitoring per room. Implementation is planned for Phase 4.

## Planned Scope

Each room will have a small ESP32 board running ESPHome firmware that reports sensor data directly to Home Assistant over WiFi. This eliminates the need for cloud services and provides low-latency local sensor readings.

**Per-room sensors planned:**
- Temperature (DHT22 or BME280)
- Humidity (DHT22 or BME280)
- Motion (PIR sensor — for presence detection and auto-lighting)
- Air quality / CO2 (MQ-135 or SCD40 for more accurate readings)

## How ESPHome Works

ESPHome is a YAML-configured firmware system for ESP32 and ESP8266 boards. You write a YAML config file describing which sensors are wired to which GPIO pins and what Home Assistant entities they should create. ESPHome compiles the firmware and flashes it to the board. After that, the board connects to WiFi and automatically appears in Home Assistant as a new device with all its sensor entities.

Documentation: https://esphome.io

## Directory Structure (when implemented)

```
esp32-sensors/
└── esphome/
    ├── living_room.yaml    # ESPHome config for living room board
    ├── bedroom.yaml        # ESPHome config for bedroom board
    ├── office.yaml         # ESPHome config for office/studio board
    └── secrets.yaml        # WiFi credentials and HA API key (not committed to git)
```

## Hardware Per Room (approximate cost)

- ESP32 dev board (ESP32-WROOM-32): $5–10 CAD
- BME280 (temp + humidity + pressure): $5–10 CAD
- PIR motion sensor (HC-SR501): $3–5 CAD
- SCD40 CO2 sensor (optional, more accurate): $20–30 CAD
- Small enclosure: $5–10 CAD

Total per room: $20–60 CAD depending on sensors chosen.
