# Norwegian Maritime Tracker for Home Assistant 🚢

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/EAasen/ha-marinetraffic-tracker/actions/workflows/ci.yml)

Official Kystverket AIS maritime tracker for Home Assistant. Real-time vessel tracking in Norwegian waters using the Norwegian Coastal Administration live AIS feed exposed through BarentsWatch.

## Documentation

| Guide | Description |
|---|---|
| [Installation](docs/installation.md) | HACS and manual installation steps |
| [Configuration](docs/configuration.md) | BarentsWatch credentials, config flow walkthrough, all options |
| [Usage](docs/usage.md) | Entities, automations, and Lovelace card examples |
| [Troubleshooting](docs/troubleshooting.md) | Common issues, log instructions, connection testing |
| [Development](docs/development.md) | Setup, testing, linting, and contribution guidelines |
| [Architecture](docs/architecture.md) | Integration structure and data flow for developers |

---

## Quick Start

### 1. Install via HACS

1. Open **HACS** in Home Assistant.
2. Click **⋮ → Custom repositories**, add `https://github.com/EAasen/ha-marinetraffic-tracker`, category **Integration**.
3. Install **Norwegian Maritime Tracker** and **restart Home Assistant**.

> **Manual install:** copy `custom_components/marinetraffic_tracker/` into `/config/custom_components/` and restart.

### 2. Get free BarentsWatch credentials

1. Create an account at <https://www.barentswatch.no/mine-side/>.
2. Register a client application and note the **Client ID** and **Client Secret**.

### 3. Add the integration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Norwegian Maritime Tracker**.
3. Follow the setup wizard — pick a radius or bounding box, enter your credentials, and set the update interval.

---

## Features

- Track vessels inside a **radius** or **bounding box** using the official Kystverket / BarentsWatch AIS feed
- Rich AIS telemetry exposed as Home Assistant entities:

  | Attribute | Description |
  |---|---|
  | `mmsi` | Unique vessel identifier |
  | `vessel_name` | Vessel name |
  | `vessel_type` | AIS vessel category (Cargo, Tanker, Passenger, …) |
  | `speed_knots` | Speed over ground |
  | `course` | Course over ground (degrees) |
  | `heading` | True heading (degrees) |
  | `status` | AIS navigational status |
  | `destination` | Destination port |
  | `eta` | Estimated time of arrival |
  | `imo` | IMO number |
  | `callsign` | Radio callsign |
  | `draught` | Draught in metres |
  | `rate_of_turn` | Rate of turn (°/min) |
  | `msgtime` | Last AIS message timestamp |

- One **vessel count sensor** plus per-vessel **sensors** and **device_tracker** entities
- **Position history** — last 20 GPS positions per vessel
- **Maritime statistics** sensor — most frequent visitor, speed record, busiest hour, and more
- Optional **vessel-type filter** — track only the categories you care about
- Optional **anchored / moored vessel exclusion** — hide stationary vessels from the live map

---

## What changed for v1.0.0

Version 1.0.0 pivots the integration to a single, official Norwegian data source:

- **Primary source:** Kystverket / BarentsWatch live AIS
- **Default focus:** Norwegian waters
- **Setup flow:** simplified to Norwegian area selection plus BarentsWatch credentials

Earlier scraping-based sources (MarineTraffic, VesselFinder, AISHub) are **deprecated** in the main v1.0.0 flow.  Multi-source support is planned for a future v2.0.0 release.

---

## Notes

- The integration domain remains `marinetraffic_tracker` for compatibility with existing installs.
- The active code path uses the official Norwegian feed instead of scraper-first logic.
- International and multi-source tracking is planned for a later v2.0.0 roadmap release.
