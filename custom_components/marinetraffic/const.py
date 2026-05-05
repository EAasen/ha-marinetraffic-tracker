"""Constants for the MarineTraffic Tracker integration."""

DOMAIN = "marinetraffic"

# Configuration keys
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADIUS = "radius"

# Defaults
DEFAULT_RADIUS = 50  # kilometres
DEFAULT_NAME = "MarineTraffic"

# Polling
SCAN_INTERVAL = 60  # seconds
JITTER_MIN = 1  # seconds
JITTER_MAX = 5  # seconds

# Entity / staleness
VESSEL_TIMEOUT = 600  # 10 minutes in seconds

# Platforms
PLATFORMS = ["sensor", "device_tracker"]

# Attribute names exposed on vessel sensors / trackers
ATTR_MMSI = "mmsi"
ATTR_VESSEL_TYPE = "vessel_type"
ATTR_STATUS = "status"
ATTR_SPEED = "speed_knots"
ATTR_HEADING = "heading"
ATTR_COURSE = "course"
ATTR_ORIGIN = "origin"
ATTR_DESTINATION = "destination"
ATTR_ETA = "eta"
ATTR_VESSEL_NAME = "vessel_name"
ATTR_FLAG = "flag"
ATTR_IMO = "imo"
ATTR_CALLSIGN = "callsign"
ATTR_LENGTH = "length"

# MarineTraffic map zoom level used for tile requests
MAP_ZOOM = 10

# HTTP client
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30  # seconds

# Vessel type mapping (MarineTraffic AIS ship type → human-readable)
VESSEL_TYPE_MAP = {
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
    56: "Spare (local vessel)",
    57: "Spare (local vessel)",
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

# AIS navigation status mapping
NAV_STATUS_MAP = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by her draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved (HSC)",
    10: "Reserved (WIG)",
    11: "Reserved",
    12: "Reserved",
    13: "Reserved",
    14: "AIS-SART / MOB-AIS / EPIRB-AIS active",
    15: "Undefined",
}
