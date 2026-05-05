# MarineTraffic Tracker for Home Assistant 🚢

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml)

A Home Assistant integration that tracks real-time maritime traffic within a specified radius or geographic boundary. Inspired by the `home-assistant-flightradar24` project, this integration identifies ships, their heading, destination, and speed without requiring a paid MarineTraffic API account.

**Integration domain:** `marinetraffic_tracker`

## ✨ Features

- **Boundary Tracking:** Monitor vessels within a circular radius or a coordinate-based bounding box.
- **Vessel Type Filter:** Optionally restrict tracking to specific vessel types (cargo, tanker, passenger, etc.).
- **Detailed Telemetry:** Provides vessel name, type, MMSI, status, speed, heading, and course.
- **Voyage Data:** Scrapes origin, destination, and ETA where publicly available.
- **Auto-Cleanup:** Vessels not seen within the stale timeout are automatically removed.
- **Map Integration:** Full support for the native HA Map card and `device_tracker` entities.
- **Vessel Photos:** Per-vessel entity pictures sourced from MarineTraffic via MMSI.
- **HA Bus Events:** `marinetraffic_vessel_entered` and `marinetraffic_vessel_exited` events for automation triggers.

## 📊 Entities & Attributes

The integration creates a `sensor.marinetraffic_vessel_count` for the total ships in range.

Per-vessel entities (sensor and device tracker) are **disabled by default** to avoid overwhelming the entity registry in busy ports — enable individual vessels as needed.

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

## 🤖 Automation Events

The integration fires two events on the Home Assistant event bus:

- `marinetraffic_vessel_entered` — fired when a vessel first appears in the tracking area
- `marinetraffic_vessel_exited` — fired when a vessel leaves or ages out of the tracking area

**Event payload fields:** `mmsi`, `name`, `vessel_type`, `latitude`, `longitude`, `destination`, `eta`, `entry_id`

Example automation trigger:
```yaml
trigger:
  - platform: event
    event_type: marinetraffic_vessel_entered
    event_data:
      vessel_type: 70  # Cargo vessel
```

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
3. Choose tracking mode: **Radius** (circle around a point) or **Bounding Box**.
4. Enter your geographic parameters.
5. Set the **Update Interval** (minimum 30 seconds), **Stale Vessel Timeout**, and optionally a **Vessel Type Filter**.

Settings can be adjusted later via the integration's **Configure** button without removing and re-adding the integration.

## ⚠️ Disclaimer & Rate Limiting

This integration uses web-scraping techniques to fetch data from MarineTraffic's public live map.
- **Use at your own risk:** Polling faster than 30 seconds may result in a temporary IP ban from MarineTraffic. The integration enforces a minimum 30-second interval automatically.
- This project is not affiliated with, authorized, or endorsed by MarineTraffic.com.
