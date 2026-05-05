"""Constants for the MarineTraffic Tracker integration."""

from __future__ import annotations

DOMAIN = "marinetraffic_tracker"

# ---------------------------------------------------------------------------
# State attribute keys — used by device_tracker and sensor platforms
# ---------------------------------------------------------------------------
ATTR_MMSI = "mmsi"
ATTR_VESSEL_NAME = "vessel_name"
ATTR_VESSEL_TYPE = "vessel_type"
ATTR_SPEED = "speed_knots"
ATTR_HEADING = "heading"
ATTR_COURSE = "course"
ATTR_STATUS = "status"
ATTR_ORIGIN = "origin"
ATTR_DESTINATION = "destination"
ATTR_ETA = "eta"
ATTR_IMO = "imo"
ATTR_CALLSIGN = "callsign"
ATTR_LENGTH = "length"
ATTR_FLAG = "flag"
ATTR_LAST_SEEN = "last_seen"

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
# List of AIS vessel type codes the user wants to track.
# Empty list / unset = track all vessel types (no filter applied).
CONF_FILTER_VESSEL_TYPES = "filter_vessel_types"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TRACKING_MODE = TRACKING_MODE_RADIUS
DEFAULT_RADIUS_KM = 50.0
DEFAULT_UPDATE_INTERVAL = 60  # seconds
DEFAULT_STALE_TIMEOUT = 600  # seconds (10 minutes)
DEFAULT_JITTER_MAX = 10  # seconds of random pre-request delay

# ---------------------------------------------------------------------------
# Anti-ban / rate-limit safety floor (seconds).
# Polling faster than this risks a temporary IP ban from MarineTraffic.
# The config flow schema enforces this as a minimum; the coordinator also
# clamps at runtime so that manually-edited config entries cannot bypass it.
# ---------------------------------------------------------------------------
MIN_UPDATE_INTERVAL = 30

# ---------------------------------------------------------------------------
# HA bus event names fired by the coordinator
# ---------------------------------------------------------------------------
EVENT_VESSEL_ENTERED = "marinetraffic_vessel_entered"
EVENT_VESSEL_EXITED = "marinetraffic_vessel_exited"

# ---------------------------------------------------------------------------
# MMSI-based vessel photo URL helper
# MarineTraffic exposes vessel photos at a deterministic URL.
# NOTE: MarineTraffic's URL path uses "shipid" as the query segment name,
# but the value supplied is the vessel's MMSI (Maritime Mobile Service
# Identity).  The placeholder in the template string below is named {mmsi}
# for clarity in the Python code; it is substituted into the "shipid:" path
# segment at runtime.
# The helper returns None for invalid/missing MMSI values so callers can
# fall back to the entity icon gracefully.
# ---------------------------------------------------------------------------
_VESSEL_PHOTO_URL = "https://www.marinetraffic.com/en/photos/of/vessels/shipid:{mmsi}/"


def vessel_photo_url(mmsi: str | None) -> str | None:
    """Return an MMSI-based vessel photo URL, or ``None`` for invalid MMSI.

    A valid MMSI is a 9-digit numeric string.  Any other value returns
    ``None`` so callers never expose a broken URL as ``entity_picture``.
    """
    if not mmsi or not isinstance(mmsi, str):
        return None
    stripped = mmsi.strip()
    if not stripped.isdigit() or len(stripped) != 9:
        return None
    return _VESSEL_PHOTO_URL.format(mmsi=stripped)


# ---------------------------------------------------------------------------
# Vessel type → MDI icon mapping (based on AIS vessel type codes)
# EXTENSION POINT: add more type codes and icons as needed.
# ---------------------------------------------------------------------------
VESSEL_TYPE_ICONS: dict[int, str] = {
    30: "mdi:fish",  # Fishing
    36: "mdi:sail-boat",  # Sailing vessel
    37: "mdi:sail-boat",  # Pleasure craft / recreational sailing
    60: "mdi:ferry",  # Passenger
    61: "mdi:ferry",
    62: "mdi:ferry",
    63: "mdi:ferry",
    64: "mdi:ferry",
    70: "mdi:ship-wheel",  # Cargo
    71: "mdi:ship-wheel",
    72: "mdi:ship-wheel",
    79: "mdi:ship-wheel",
    80: "mdi:water",  # Tanker (no dedicated tanker icon in MDI core)
    81: "mdi:water",
    89: "mdi:water",
}
DEFAULT_VESSEL_ICON = "mdi:ferry"

# ---------------------------------------------------------------------------
# Vessel type code → human-readable name (AIS ship type codes)
# ---------------------------------------------------------------------------
VESSEL_TYPE_MAP: dict[int, str] = {
    0: "Unknown",
    20: "Wing in Ground",
    21: "Wing in Ground (hazardous A)",
    22: "Wing in Ground (hazardous B)",
    23: "Wing in Ground (hazardous C)",
    24: "Wing in Ground (hazardous D)",
    29: "Wing in Ground (no other information)",
    30: "Fishing",
    31: "Towing",
    32: "Towing (large)",
    33: "Dredging",
    34: "Diving",
    35: "Military",
    36: "Sailing",
    37: "Pleasure Craft",
    40: "High Speed Craft",
    41: "High Speed Craft (hazardous A)",
    42: "High Speed Craft (hazardous B)",
    43: "High Speed Craft (hazardous C)",
    44: "High Speed Craft (hazardous D)",
    49: "High Speed Craft (no additional information)",
    50: "Pilot Vessel",
    51: "Search and Rescue",
    52: "Tug",
    53: "Port Tender",
    54: "Anti-pollution",
    55: "Law Enforcement",
    58: "Medical Transport",
    59: "Non-combatant ship",
    60: "Passenger",
    61: "Passenger (hazardous A)",
    62: "Passenger (hazardous B)",
    63: "Passenger (hazardous C)",
    64: "Passenger (hazardous D)",
    69: "Passenger (no additional information)",
    70: "Cargo",
    71: "Cargo (hazardous A)",
    72: "Cargo (hazardous B)",
    73: "Cargo (hazardous C)",
    74: "Cargo (hazardous D)",
    79: "Cargo (no additional information)",
    80: "Tanker",
    81: "Tanker (hazardous A)",
    82: "Tanker (hazardous B)",
    83: "Tanker (hazardous C)",
    84: "Tanker (hazardous D)",
    89: "Tanker (no additional information)",
    90: "Other",
    91: "Other (hazardous A)",
    92: "Other (hazardous B)",
    93: "Other (hazardous C)",
    94: "Other (hazardous D)",
    99: "Other (no additional information)",
}
