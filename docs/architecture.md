# Architecture Guide

This document describes the internal structure of the Norwegian Maritime Tracker integration and is intended for developers who want to understand or extend the codebase.

---

## Integration Structure

```
custom_components/marinetraffic_tracker/
├── __init__.py           # Integration entry point — setup and teardown
├── manifest.json         # Integration metadata (version, dependencies)
├── const.py              # All constants, defaults, and type code maps
├── config_flow.py        # Setup wizard and options flow (UI configuration)
├── coordinator.py        # DataUpdateCoordinator — polling, state, statistics
├── client.py             # Shared VesselData dataclass and base types
├── kystverket_client.py  # Kystverket / BarentsWatch AIS API client
├── aishub_client.py      # AISHub API client (legacy / optional)
├── vesselfinder_client.py# VesselFinder scraper client (deprecated)
├── entity.py             # Shared base entity (MarineTrafficEntity)
├── sensor.py             # Sensor platform — count sensor + per-vessel sensors
├── device_tracker.py     # Device tracker platform — per-vessel trackers
├── strings.json          # UI string keys
└── translations/
    └── en.json           # English translations for the UI strings
```

---

## Component Responsibilities

### `__init__.py` — Integration Lifecycle

- Calls `hass.config_entries.async_setup_entry` during setup.
- Creates the `MarineTrafficCoordinator` and stores it in `hass.data[DOMAIN][entry_id]`.
- Forwards setup to the `sensor` and `device_tracker` platforms.
- Tears everything down on unload.

### `coordinator.py` — State Management

The `MarineTrafficCoordinator` extends Home Assistant's `DataUpdateCoordinator` and is the heart of the integration.

Responsibilities:
- **Periodic polling** with optional random jitter (up to 10 s by default) to avoid synchronised API bursts.
- **Vessel merging** — incoming `VesselData` objects are merged into the running `vessels: dict[str, VesselData]` dictionary keyed by MMSI.
- **Staleness eviction** — vessels not seen within the configured `stale_timeout` are removed from `vessels`.
- **Position history** — each vessel's recent GPS track is stored as a list of `(latitude, longitude, timestamp)` tuples (capped at `DEFAULT_HISTORY_SIZE = 20` points).
- **Anchor swing filtering** — new position history entries for anchored vessels are only recorded when the vessel has moved more than 100 m from the last recorded position.
- **Statistics** — visit counts, time-in-zone, speed and size records, and hourly/daily traffic patterns are maintained in a separate `statistics` dict and survive vessel eviction.

### `client.py` — Shared Data Types

Defines the `VesselData` dataclass used by all clients and the entity layer.  All fields are optional to accommodate data sources that provide partial information.

### `kystverket_client.py` — Primary Data Source

Makes authenticated OAuth2 requests to the BarentsWatch live AIS endpoint.  Handles token acquisition, token refresh, and translating the API JSON response into `VesselData` objects.

### `entity.py` — Base Entity

`MarineTrafficEntity` extends `CoordinatorEntity` and provides:
- A consistent `unique_id` scheme (`<entry_id>_<mmsi>`).
- Device info linking all vessel entities to a single device per config entry.
- A convenience method for checking whether an MMSI is still active.

### `sensor.py` — Sensor Platform

- **`MarineTrafficCountSensor`** — a single sensor per config entry reporting the number of active vessels.
- **`MarineTrafficVesselSensor`** — one sensor per vessel, dynamically created the first time a new MMSI is seen.  Becomes `unavailable` once the vessel is evicted.
- **`MarineTrafficStatisticsSensor`** — reports lifetime statistics from the coordinator.

### `device_tracker.py` — Device Tracker Platform

- **`MarineTrafficVesselTracker`** — one tracker per vessel, exposing `latitude` and `longitude` for map integration.  Dynamically created alongside the vessel sensor.

### `config_flow.py` — UI Configuration

A multi-step `ConfigFlow` for initial setup and an `OptionsFlow` for changing settings after setup.  Steps:
1. Tracking mode selection (radius or bounding box).
2. Area selection (map picker or coordinate fields).
3. BarentsWatch credentials.
4. Update interval, stale timeout, vessel type filter, and anchored vessel exclusion.

---

## Data Flow

```
BarentsWatch API
      │
      ▼
KystverketClient.get_vessels_in_radius()
  or .get_vessels_in_box()
      │  returns List[VesselData]
      ▼
MarineTrafficCoordinator._async_update_data()
  ├─ merge new VesselData into self.vessels dict
  ├─ evict stale vessels
  ├─ update position history per vessel
  └─ update statistics
      │  coordinator notifies listeners
      ▼
┌─────────────────────────────────┐
│  MarineTrafficCountSensor       │ ← reads len(coordinator.vessels)
│  MarineTrafficVesselSensor (×N) │ ← reads coordinator.vessels[mmsi]
│  MarineTrafficVesselTracker (×N)│ ← reads coordinator.vessels[mmsi]
│  MarineTrafficStatisticsSensor  │ ← reads coordinator.statistics
└─────────────────────────────────┘
      │
      ▼
Home Assistant state machine → Lovelace / Automations
```

---

## Entity Creation Process

New entities are created dynamically when the coordinator delivers an update containing a previously-unseen MMSI.  The process:

1. `async_setup_entry` in `sensor.py` / `device_tracker.py` registers a coordinator listener via `coordinator.async_add_listener`.
2. On each coordinator update, the listener checks `coordinator.vessels` for MMSIs that do not yet have an entity.
3. New `MarineTrafficVesselSensor` / `MarineTrafficVesselTracker` objects are instantiated for new MMSIs and passed to `async_add_entities`.
4. When a vessel is evicted from `coordinator.vessels`, its entity's `available` property returns `False`, which Home Assistant renders as *unavailable*.  The entity remains in the entity registry so history is preserved.

---

## Key Constants (const.py)

| Constant | Purpose |
|---|---|
| `MIN_UPDATE_INTERVAL` | Hard floor (30 s) for scraper-based sources |
| `MIN_UPDATE_INTERVAL_API` | Hard floor (5 s) for API-based sources |
| `DEFAULT_HISTORY_SIZE` | Maximum GPS track points per vessel (20) |
| `ANCHOR_SWING_THRESHOLD_KM` | Minimum movement to record a new history point for anchored vessels (0.1 km) |
| `ANCHORED_STATUSES` | AIS status strings treated as stationary (`{"At Anchor", "Moored"}`) |
| `VESSEL_TYPE_MAP` | AIS type code → human-readable name |
| `VESSEL_TYPE_ICONS` | AIS type code → MDI icon name |
| `NAV_STATUS_MAP` | AIS navigational status code → human-readable name |
