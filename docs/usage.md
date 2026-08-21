# Usage Guide

This guide explains the entities created by Norwegian Maritime Tracker and shows common automation and Lovelace card examples.

---

## Entities Created

### Vessel Count Sensor

**Entity ID format:** `sensor.<entry_name>_vessel_count`

| Attribute | Description |
|---|---|
| State | Number of active vessels currently in the monitored area |
| `anchored_vessel_count` | Number of anchored / moored vessels in the area |
| `anchored_vessels` | List of MMSI + name pairs for anchored vessels |

### Per-vessel Sensor

One sensor is created for each vessel that appears in the monitored area.

**Entity ID format:** `sensor.<entry_name>_vessel_<mmsi>`

| Attribute | Type | Description |
|---|---|---|
| State | string | Vessel name |
| `mmsi` | string | Maritime Mobile Service Identity (unique vessel ID) |
| `vessel_name` | string | Vessel name from AIS broadcast |
| `vessel_type` | string | Human-readable vessel category (e.g. *Cargo*, *Tanker*) |
| `speed_knots` | float | Speed over ground in knots |
| `course` | float | Course over ground in degrees (0–360) |
| `heading` | float | True heading in degrees |
| `status` | string | AIS navigational status (e.g. *Under Way Using Engine*) |
| `destination` | string | Destination port as broadcast by the vessel |
| `eta` | string | Estimated time of arrival (ISO-8601) |
| `imo` | string | IMO ship identification number |
| `callsign` | string | Radio callsign |
| `draught` | float | Draught in metres |
| `rate_of_turn` | float | Rate of turn in degrees per minute |
| `msgtime` | string | Timestamp of the last AIS message |
| `last_seen` | string | Timestamp when the vessel was last seen by the integration |
| `length` | float | Vessel length in metres |
| `beam` | float | Vessel beam (width) in metres |
| `flag` | string | Flag state / country code |
| `data_source` | string | Which data source provided this vessel's data |
| `position_history` | list | Recent GPS track points (up to 20 positions) |

### Per-vessel Device Tracker

One device-tracker entity is created for each vessel.  Device trackers expose `latitude` and `longitude` directly, which makes them compatible with the Home Assistant **Map** card and **Person** tracking.

**Entity ID format:** `device_tracker.<entry_name>_vessel_<mmsi>`

The device tracker includes the same AIS attributes as the per-vessel sensor.

### Statistics Sensor

**Entity ID format:** `sensor.<entry_name>_statistics`

| Attribute | Description |
|---|---|
| `most_frequent_visitor` | MMSI + name of the vessel seen most often |
| `longest_resident` | Vessel that spent the most cumulative time in the area |
| `speed_record` | Highest speed recorded for any single vessel |
| `largest_vessel` | Longest vessel seen |
| `smallest_vessel` | Shortest vessel seen |
| `busiest_hour` | Hour of day (0–23) with the most vessel sightings |
| `busiest_day` | Day of week with the most vessel sightings |
| `hourly_counts` | Dict mapping hour → count |
| `daily_counts` | Dict mapping weekday name → count |
| `total_vessels_seen` | Total unique MMSIs observed since the integration was set up |

---

## Map Card

The device-tracker entities appear automatically on Home Assistant's built-in **Map** card.  To add a map card showing all tracked vessels:

```yaml
type: map
entities:
  - device_tracker.my_area_vessel_123456789
  - device_tracker.my_area_vessel_987654321
# Or use a group / label to include all vessel trackers
```

For a dynamic map that updates as new vessels are detected, use a label or a [custom card](https://github.com/custom-cards/lovelace-home-assistant-ais-tracker) that queries entities by domain.

---

## Automation Examples

### Notify when a passenger ferry enters the area

```yaml
automation:
  alias: "Ferry arrived"
  trigger:
    - platform: state
      entity_id: sensor.my_area_vessel_count
  condition:
    - condition: template
      value_template: >
        {% set vessels = states.sensor
           | selectattr('entity_id', 'search', 'vessel_')
           | list %}
        {% for v in vessels %}
          {% if v.attributes.get('vessel_type') == 'Passenger' %}
            true
          {% endif %}
        {% endfor %}
  action:
    - service: notify.mobile_app_my_phone
      data:
        message: "A passenger vessel is now in the area."
```

### Alert when vessel count drops to zero (harbour cleared)

```yaml
automation:
  alias: "Harbour empty"
  trigger:
    - platform: numeric_state
      entity_id: sensor.my_area_vessel_count
      to: "0"
  action:
    - service: notify.notify
      data:
        message: "No vessels currently in the monitored area."
```

### Track a specific vessel by MMSI

If you know a vessel's MMSI (e.g. `123456789`), you can reference its entity directly:

```yaml
automation:
  alias: "My yacht arrived"
  trigger:
    - platform: state
      entity_id: device_tracker.my_area_vessel_123456789
      to: "home"
  action:
    - service: notify.notify
      data:
        message: "Your yacht is back in the harbour!"
```

### Presence detection — vessel in zone

```yaml
automation:
  alias: "Vessel entered port zone"
  trigger:
    - platform: zone
      entity_id: device_tracker.my_area_vessel_123456789
      zone: zone.my_harbour
      event: enter
  action:
    - service: notify.notify
      data:
        message: >
          {{ state_attr('device_tracker.my_area_vessel_123456789', 'vessel_name') }}
          has entered the harbour zone.
```

---

## Lovelace Card Suggestions

### Entities card — vessel details

```yaml
type: entities
title: "Vessel Details"
entities:
  - entity: sensor.my_area_vessel_123456789
    name: "Vessel Name"
  - type: attribute
    entity: sensor.my_area_vessel_123456789
    attribute: speed_knots
    name: "Speed (kn)"
  - type: attribute
    entity: sensor.my_area_vessel_123456789
    attribute: destination
    name: "Destination"
  - type: attribute
    entity: sensor.my_area_vessel_123456789
    attribute: status
    name: "Status"
```

### Statistics glance card

```yaml
type: glance
title: "Maritime Statistics"
entities:
  - entity: sensor.my_area_vessel_count
    name: "Active"
  - entity: sensor.my_area_statistics
    name: "Statistics"
    attribute: total_vessels_seen
```
