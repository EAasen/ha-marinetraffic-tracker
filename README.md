# MarineTraffic Tracker for Home Assistant 🚢

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml)

A Home Assistant integration that tracks real-time maritime traffic within a specified radius or geographic boundary. Inspired by the `home-assistant-flightradar24` project, this integration identifies ships, their heading, destination, and speed without requiring a paid MarineTraffic API account.

> **RC1** — Production-grade release candidate. Domain: `marinetraffic_tracker`.

## ✨ Features

- **Boundary Tracking:** Monitor vessels within a circular radius or a coordinate-based bounding box.
- **Vessel Type Filtering:** Filter tracking to specific AIS vessel types (Cargo, Tanker, Passenger, etc.) — empty selection means all types are tracked.
- **Detailed Telemetry:** Provides vessel name, type, MMSI, status, speed, heading, and course.
- **Voyage Data:** Scrapes origin, destination, and ETA where publicly available.
- **Auto-Cleanup:** Entities are automatically removed when a ship leaves your tracking zone.
- **Map Integration:** Full support for the native HA Map card and `device_tracker` entities.
- **HA Bus Events:** Fires `marinetraffic_vessel_entered` and `marinetraffic_vessel_exited` for easy automations.
- **Vessel Photos:** Entity picture support using MMSI-based photo URLs.
- **Anti-ban Safety:** Enforced minimum polling interval of 30 seconds to reduce MarineTraffic rate-limit risk.

## 📊 Entities & Attributes

### Aggregate (always enabled)

| Entity | Description |
| :--- | :--- |
| `sensor.vessel_count` | Total vessels currently tracked in the area |

### Per-vessel (disabled by default)

Per-vessel sensor and device tracker entities are **disabled by default** to prevent entity explosion in busy ports. Enable individual vessels from **Settings → Devices & Services → Entities**.

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

## 🔔 HA Bus Events

Two events are fired on the Home Assistant event bus for automation use:

| Event | Fired when |
| :--- | :--- |
| `marinetraffic_vessel_entered` | A vessel first appears in the tracked/filtered set |
| `marinetraffic_vessel_exited` | A vessel leaves the area or ages out of the stale timeout |

**Event payload:**
```yaml
mmsi: "123456789"
name: "MY VESSEL"
vessel_type: 70
latitude: 59.9
longitude: 10.7
destination: "OSLO"
eta: "2024-01-15 08:00"
entry_id: "abc123"
```

**Example automation:**
```yaml
automation:
  trigger:
    platform: event
    event_type: marinetraffic_vessel_entered
  action:
    service: notify.mobile_app
    data:
      message: "{{ trigger.event.data.name }} has entered the area!"
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
3. Choose tracking mode: **Radius** (center + km) or **Bounding Box** (N/E/S/W coordinates).
4. Set the **Update Interval** (minimum 30 seconds, default 60 seconds).
5. Optionally select **Vessel Types** to filter — leave empty to track all types.

### Options (after setup)
All timing and filtering settings can be adjusted without removing and re-adding the integration:
- Go to **Settings** → **Devices & Services** → **MarineTraffic Tracker** → **Configure**.

## ⚠️ Disclaimer & Rate Limiting

This integration uses web-scraping techniques to fetch data from MarineTraffic's public live map.

- **Minimum poll interval of 30 seconds** is enforced both in the UI and at runtime to reduce IP ban risk.
- Use at your own risk: excessive polling may still result in a temporary IP ban from MarineTraffic.
- This project is not affiliated with, authorized, or endorsed by MarineTraffic.com.

