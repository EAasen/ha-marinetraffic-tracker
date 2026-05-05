# MarineTraffic Tracker for Home Assistant 🚢

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant integration that tracks real-time maritime traffic within a specified radius or geographic boundary. Inspired by the `home-assistant-flightradar24` project, this integration identifies ships, their heading, destination, and speed without requiring a paid MarineTraffic API account.

## ✨ Features

- **Boundary Tracking:** Monitor vessels within a circular radius or a coordinate-based bounding box.
- **Detailed Telemetry:** Provides vessel name, type, MMSI, status, speed, heading, and course.
- **Voyage Data:** Scrapes origin, destination, and ETA where publicly available.
- **Auto-Cleanup:** Entities are automatically removed when a ship leaves your tracking zone.
- **Map Integration:** Full support for the native HA Map card and `device_tracker` entities.

## 📊 Entities & Attributes

The integration creates a `sensor.marinetraffic_count` for the total ships in range, and individual `sensor.vessel_[name]` entities with the following attributes:

| Attribute | Description |
| :--- | :--- |
| `mmsi` | Maritime Mobile Service Identity |
| `vessel_type` | Type (Cargo, Tanker, Passenger, etc.) |
| `status` | Current state (Under way, At anchor, Moored) |
| `speed_knots` | Current speed in knots |
| `heading` | Direction the ship is pointing |
| `origin` | Port of departure |
| `destination` | Destination port |
| `eta` | Estimated Time of Arrival |

## 🚀 Installation

### Option 1: HACS (Recommended)
1. Open **HACS** in Home Assistant.
2. Click the three dots in the top right and select **Custom repositories**.
3. Add `https://github.com/EAasen/ha-marinetraffic-tracker` with category **Integration**.
4. Click **Install**.
5. Restart Home Assistant.

### Option 2: Manual
1. Download the `custom_components/marinetraffic_tracker` folder.
2. Copy it into your Home Assistant `/config/custom_components/` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

Configuration is handled entirely via the UI:
1. Go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **MarineTraffic Tracker**.
3. Enter your center coordinates (or use Home Assistant defaults) and set your tracking radius (km).
4. Set the **Update Interval** (Default: 60 seconds).

## ⚠️ Disclaimer & Rate Limiting

This integration uses web-scraping techniques to fetch data from MarineTraffic's public live map. 
- **Use at your own risk:** Excessive polling (less than 30s) may result in a temporary IP ban from MarineTraffic.
- This project is not affiliated with, authorized, or endorsed by MarineTraffic.com.
