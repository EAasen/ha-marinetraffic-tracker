# Norwegian Maritime Tracker for Home Assistant 🚢

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Official Kystverket AIS maritime tracker for Home Assistant. Real-time vessel tracking in Norwegian waters using the Norwegian Coastal Administration live AIS feed exposed through BarentsWatch.

## What changed for v1.0.0

Version 1.0.0 pivots the integration to a single, official Norwegian data source:

- **Primary source:** Kystverket / BarentsWatch live AIS
- **Default focus:** Norwegian waters
- **Setup flow:** simplified to Norwegian area selection plus BarentsWatch credentials

Earlier scraping-based sources such as MarineTraffic, VesselFinder, and AISHub are now considered **deprecated for the main v1.0.0 flow**. A future v2.0.0 may reintroduce multi-source support.

## Features

- Track vessels inside a **radius** or **bounding box**
- Map core AIS telemetry into Home Assistant entities:
  - `mmsi`
  - `vessel_name`
  - `speed_knots`
  - `heading`
  - `status`
- Create one vessel count sensor plus per-vessel sensors and `device_tracker` entities
- Optional vessel-type filtering
- Optional exclusion of anchored and moored vessels from the live map

## Installation

### HACS

1. Open **HACS** in Home Assistant.
2. Add `https://github.com/EAasen/ha-marinetraffic-tracker` as a custom repository.
3. Install the integration.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/marinetraffic_tracker` into `/config/custom_components/`.
2. Restart Home Assistant.

## Configuration

Configuration is handled in the Home Assistant UI:

1. Go to **Settings → Devices & Services**.
2. Add **Norwegian Maritime Tracker**.
3. Choose a **radius** or **bounding box** in Norwegian waters.
4. Enter your free **BarentsWatch Client ID** and **Client Secret**.
5. Choose the update interval and stale timeout.

## BarentsWatch credentials

The integration uses the official BarentsWatch AIS API. You need free API credentials:

1. Create an account at BarentsWatch.
2. Register an application/client.
3. Copy the generated client ID and client secret into the integration setup.

## Notes

- The integration domain remains `marinetraffic_tracker` for compatibility with existing installs.
- The active code path now uses the official Norwegian feed instead of scraper-first logic.
- International and multi-source tracking is planned for a later v2.0.0 roadmap release.
