## Summary

Three standard AIS fields are currently absent from `VesselData` and the rest of the integration. Adding them would make the integration more useful for routing automations and vessel-size filtering.

---

## Fields to add

| Field | AIS Message type(s) | Raw API key (expected) | Description |
|---|---|---|---|
| `draught` | Type 5 | `DRAUGHT` | Vessel draught in **decimetres** (manually entered by crew). Useful for shallow-water automations. |
| `rate_of_turn` | Type 1, 2, 3 | `ROT` | Rate of turn in **degrees/minute** (positive = turning right). Values: –128 = no turn info; –127/+127 = turning at > 5°/30 s. Useful for predicting vessel trajectory in automations. |
| `beam` | Type 5, Type 19 | Derived from antenna offsets `A`, `B`, `C`, `D` | Vessel beam (width) in metres. MarineTraffic does not expose beam directly; it must be derived as `C + D` from the AIS antenna-position offsets reported in Message 5. |

---

## Work required

### 1. `client.py` — `VesselData`

Add three new optional fields to the `@dataclass`:

```python
draught: float | None = None      # decimetres
rate_of_turn: int | None = None   # degrees/minute; –128 = no info
beam: int | None = None           # metres (derived from C + D offsets)
```

### 2. `client.py` — `_parse_row`

- Parse `DRAUGHT` → `float` (with safe fallback for `None`/invalid).
- Parse `ROT` → `int` (with safe fallback; –128 = "no turn info", represent as `None`).
- Parse antenna offsets `C` and `D` → `beam = int(C) + int(D)` with safe fallback.
- Update the `_parse_response` docstring example to include the new keys.

### 3. `const.py` — new `ATTR_*` constants

```python
ATTR_DRAUGHT = "draught"
ATTR_RATE_OF_TURN = "rate_of_turn"
ATTR_BEAM = "beam"
```

### 4. `sensor.py` — `extra_state_attributes`

Import and expose `ATTR_DRAUGHT`, `ATTR_RATE_OF_TURN`, `ATTR_BEAM` in `MarineTrafficVesselSensor.extra_state_attributes`.

### 5. `device_tracker.py` — `extra_state_attributes`

Same imports and additions as above so both entity types remain consistent.

### 6. `README.md`

Add the three fields to the attribute reference table.

### 7. Tests

- Extend `tests/test_client.py` to cover:
  - `_parse_row` correctly parses `DRAUGHT`, `ROT`, `C`+`D` offsets.
  - Safe fallbacks for missing / non-numeric values.
- Extend `tests/test_sensor_attributes.py` to verify both sensor and tracker expose the new keys.

---

## Acceptance criteria

- [ ] `draught`, `rate_of_turn`, `beam` fields present in `VesselData`.
- [ ] `_parse_row` populates all three from the raw API dict with safe fallbacks.
- [ ] Three new `ATTR_*` constants added to `const.py`.
- [ ] Both `sensor.py` and `device_tracker.py` expose the new attributes.
- [ ] `README.md` attribute table updated.
- [ ] All new code covered by tests; all existing tests still pass.
- [ ] Ruff, HASSfest, and Pytest all green.

---

## Notes

- `beam` is **not** a directly-transmitted AIS field; it is derived from the four antenna-position offsets (A fore, B aft, C starboard, D port) from Message 5. MarineTraffic may expose these as `C` and `D` separately — verify against live data (see also the Verification issue).
- `rate_of_turn` value –128 (0x80) means "no turn information available". Consider mapping this to `None` rather than exposing the raw sentinel to users.
- `draught` is a manual entry from the vessel's crew and may be inaccurate or missing for many vessels.

_Originated from the non-blocking items noted in PR #19._
