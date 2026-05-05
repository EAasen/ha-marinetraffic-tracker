# MarineTraffic Tracker for Home Assistant 🚢

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml)

A Home Assistant integration that tracks real-time maritime traffic within a specified radius or geographic boundary. Inspired by the `home-assistant-flightradar24` project, this integration identifies ships, their heading, destination, and speed without requiring a paid MarineTraffic API account.

> **Domain:** `marinetraffic_tracker` — this is the only component domain in this repository.
> All files live under `custom_components/marinetraffic_tracker/`.

## ✨ Features

- **Boundary Tracking:** Monitor vessels within a circular radius or a coordinate-based bounding box.
- **Vessel Type Filter:** Restrict tracking to specific AIS vessel categories (Cargo, Tanker, Passenger, etc.).
- **Detailed Telemetry:** Provides vessel name, type, MMSI, status, speed, heading, and course.
- **Voyage Data:** Scrapes origin, destination, and ETA where publicly available.
- **Auto-Cleanup:** Entities are automatically removed when a ship leaves your tracking zone.
- **Map Integration:** Full support for the native HA Map card and `device_tracker` entities.
- **Vessel Photos:** Per-vessel entities show thumbnail photos via MarineTraffic's public photo endpoint (where available).
- **Automation Events:** Fires `marinetraffic_vessel_entered` and `marinetraffic_vessel_exited` bus events for use in automations.
- **Safe Polling:** A hard minimum of 30 seconds is enforced on the update interval to prevent IP bans.

## 📊 Entities & Attributes

The integration creates a `sensor.marinetraffic_count` (always enabled) for the total ships in range, and individual `sensor.vessel_[name]` + `device_tracker.vessel_[name]` entities with the following attributes:

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

> **Note:** Per-vessel entities are **disabled by default** to prevent entity explosion in busy ports.
> Enable individual vessels via **Settings → Entities** in the HA UI.

## 🔔 Automation Events

Two bus events are fired by the coordinator:

| Event | When fired | Key payload fields |
| :--- | :--- | :--- |
| `marinetraffic_vessel_entered` | First time a vessel appears in the tracking area | `mmsi`, `name`, `vessel_type`, `latitude`, `longitude`, `destination`, `eta`, `entry_id` |
| `marinetraffic_vessel_exited` | A vessel has not been seen for longer than the stale timeout | same fields with last-known values |

Example automation trigger:
```yaml
trigger:
  - platform: event
    event_type: marinetraffic_vessel_entered
    event_data:
      vessel_type: 70  # Cargo vessels only
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
3. Choose tracking mode: **Radius** (circle around a point) or **Box** (bounding box).
4. Enter coordinates and radius/boundaries.
5. Configure timing:
   - **Update Interval** (minimum 30 s, default 60 s)
   - **Stale Vessel Timeout** (default 600 s / 10 min)
   - **Vessel Type Filter** (optional — leave empty to track all types)

All timing and filter settings can be changed later via **Settings → Devices & Services → MarineTraffic Tracker → Configure**.

## ⚠️ Disclaimer & Rate Limiting

This integration uses web-scraping techniques to fetch data from MarineTraffic's public live map.
- **Use at your own risk:** Excessive polling (less than 30s) may result in a temporary IP ban from MarineTraffic.
- The minimum update interval is enforced at 30 seconds by the integration — it cannot be set lower.
- This project is not affiliated with, authorized, or endorsed by MarineTraffic.com.
