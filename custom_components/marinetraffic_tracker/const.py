"""Constants for the MarineTraffic Tracker integration."""
from __future__ import annotations

DOMAIN = "marinetraffic_tracker"

# ---------------------------------------------------------------------------
# Tracking modes
# ---------------------------------------------------------------------------
TRACKING_MODE_RADIUS = "radius"
TRACKING_MODE_BOX = "box"
TRACKING_MODES = [TRACKING_MODE_RADIUS, TRACKING_MODE_BOX]

# ---------------------------------------------------------------------------
# Configuration / options keys
# ---------------------------------------------------------------------------
CONF_TRACKING_MODE = "tracking_mode"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS_KM = "radius_km"
CONF_NORTH = "north"
CONF_EAST = "east"
CONF_SOUTH = "south"
CONF_WEST = "west"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_STALE_TIMEOUT = "stale_timeout"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TRACKING_MODE = TRACKING_MODE_RADIUS
DEFAULT_RADIUS_KM = 50.0
DEFAULT_UPDATE_INTERVAL = 60     # seconds
DEFAULT_STALE_TIMEOUT = 600      # seconds (10 minutes)
DEFAULT_JITTER_MAX = 10          # seconds of random pre-request delay

# ---------------------------------------------------------------------------
# Vessel type → MDI icon mapping (based on AIS vessel type codes)
# EXTENSION POINT: add more type codes and icons as needed.
# ---------------------------------------------------------------------------
VESSEL_TYPE_ICONS: dict[int, str] = {
    30: "mdi:fish",          # Fishing
    36: "mdi:sail-boat",     # Sailing vessel
    37: "mdi:sail-boat",     # Pleasure craft / recreational sailing
    60: "mdi:ferry",         # Passenger
    61: "mdi:ferry",
    62: "mdi:ferry",
    63: "mdi:ferry",
    64: "mdi:ferry",
    70: "mdi:ship-wheel",    # Cargo
    71: "mdi:ship-wheel",
    72: "mdi:ship-wheel",
    79: "mdi:ship-wheel",
    80: "mdi:water",         # Tanker (no dedicated tanker icon in MDI core)
    81: "mdi:water",
    89: "mdi:water",
}
DEFAULT_VESSEL_ICON = "mdi:ferry"
