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
- **Vessel Information Table:** The Vessel Count sensor exposes a `vessels` list attribute with name, MMSI, speed, status, type, position, and thumbnail URL for every active vessel — compatible with `flex-table-card`.
- **Position History:** Each vessel sensor and device tracker exposes a `position_history` attribute (up to 20 recent positions) so you can visualise historical tracks on the map.

## 📊 Entities & Attributes

The integration domain is `marinetraffic_tracker`. It creates one **Vessel Count** sensor for the total ships in range, plus individual sensor and device-tracker entities per vessel with the following attributes:

| Attribute | Description |
| :--- | :--- |
| `mmsi` | Maritime Mobile Service Identity |
| `vessel_name` | Name of the vessel |
| `vessel_type` | Type (Cargo, Tanker, Passenger, etc.) |
| `status` | Current navigational state (e.g. Under Way, At Anchor, Moored) |
| `speed_knots` | Current speed in knots |
| `heading` | Direction the ship is pointing (degrees) |
| `course` | Course over ground (degrees) |
| `origin` | Port of departure |
| `destination` | Destination port |
| `eta` | Estimated Time of Arrival |
| `imo` | IMO vessel number |
| `callsign` | Radio callsign |
| `flag` | Flag state (ISO 2-letter code) |
| `length` | Vessel length in metres |
| `draught` | Vessel draught in decimetres (crew-entered, may be absent) |
| `rate_of_turn` | Rate of turn in degrees/minute (positive = turning right; `null` when no info) |
| `beam` | Vessel beam (width) in metres, derived from AIS antenna offsets C + D |
| `last_seen` | Timestamp of last AIS observation |
| `position_history` | List of up to 20 recent positions (each with `latitude`, `longitude`, `timestamp`) |

### Vessel Count Sensor — extra attributes

| Attribute | Description |
| :--- | :--- |
| `vessel_mmsis` | Sorted list of active MMSI strings |
| `vessels` | Structured list of all active vessels (suitable for table cards — see below) |

Each entry in `vessels` contains: `mmsi`, `vessel_name`, `vessel_type`, `speed_knots`, `status`, `heading`, `destination`, `latitude`, `longitude`, `entity_picture`.

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
3. Choose a tracking mode:
   - **Radius** — enter centre coordinates and a search radius (km).
   - **Bounding Box** — enter north/east/south/west boundary coordinates.
4. Set the **Update Interval** (default: 60 s, minimum: 30 s) and **Stale Vessel Timeout** (default: 600 s).

Timing settings can be adjusted later via **Options** without removing the integration.

## 🗺️ Dashboard Examples

### Vessel Information Table (flex-table-card)

Display all active vessels as a sortable table with thumbnails using [flex-table-card](https://github.com/custom-cards/flex-table-card):

```yaml
type: custom:flex-table-card
title: Active Vessels
entities:
  include: sensor.marinetraffic_tracker_vessel_count
columns:
  - data: vessels
    modify: x.entity_picture
    name: Photo
    icon: mdi:image
  - data: vessels
    modify: x.vessel_name
    name: Vessel
  - data: vessels
    modify: x.mmsi
    name: MMSI
  - data: vessels
    modify: x.speed_knots
    name: Speed (kn)
  - data: vessels
    modify: x.status
    name: Status
  - data: vessels
    modify: x.destination
    name: Destination
```

### Historical Track on the Map

Enable the `device_tracker` entities for the vessels you want to track (via **Settings → Entities → MarineTraffic Tracker**), then add a standard Map card. Home Assistant automatically records their state history, and the Map card's built-in history mode lets you replay tracks over any time period.

To display a vessel's recent track programmatically, use the `position_history` attribute exposed by each vessel sensor or device tracker:

```yaml
# Example: template sensor that extracts the latest position from history
template:
  - sensor:
      - name: "EVER GIVEN last position"
        state: >
          {% set hist = state_attr('sensor.marinetraffic_tracker_ever_given', 'position_history') %}
          {% if hist %}{{ hist[-1].timestamp }}{% else %}unknown{% endif %}
        attributes:
          latitude: >
            {% set hist = state_attr('sensor.marinetraffic_tracker_ever_given', 'position_history') %}
            {% if hist %}{{ hist[-1].latitude }}{% endif %}
          longitude: >
            {% set hist = state_attr('sensor.marinetraffic_tracker_ever_given', 'position_history') %}
            {% if hist %}{{ hist[-1].longitude }}{% endif %}
```

## ⚠️ Disclaimer & Rate Limiting

This integration uses web-scraping techniques to fetch data from MarineTraffic's public live map. 
- **Use at your own risk:** Excessive polling (less than 30s) may result in a temporary IP ban from MarineTraffic.
- This project is not affiliated with, authorized, or endorsed by MarineTraffic.com.
