## Summary

The `_parse_response` docstring in `client.py` contains the comment **"placeholder — verify against live data"**. The field names assumed by `_parse_row` have been inferred from observation and documentation but have **not yet been confirmed against a live MarineTraffic API response** in a production Home Assistant environment.

If any field name is wrong, the corresponding attribute will silently remain `None` for every vessel — a bug that is very hard to detect without live data.

---

## Field names to verify

The following raw key names are currently assumed in `_parse_row`:

| `VesselData` field | Assumed raw key | Risk if wrong |
|---|---|---|
| `mmsi` | `MMSI` | **Critical** — vessel is skipped entirely |
| `name` | `SHIPNAME` | Medium — falls back to `"Vessel {mmsi}"` |
| `vessel_type` | `SHIPTYPE` | Medium — defaults to `0` (Unknown) |
| `latitude` | `LAT` | **Critical** — wrong position |
| `longitude` | `LON` | **Critical** — wrong position |
| `heading` | `HEADING` | Low — silently `None` |
| `course` | `COURSE` | Low — silently `None` |
| `speed` | `SPEED` | Low — silently `None` |
| `status` | `NAVSTAT` | Low — silently `None` |
| `origin` | `LASTPORT` | Low — silently `None` |
| `destination` | `DESTINATION` | Low — silently `None` |
| `eta` | `ETA_CALC` | Low — silently `None` |
| `imo` | `IMO` | Low — silently `None` |
| `flag` | `FLAG` | Low — silently `None` |
| `callsign` | `CALLSIGN` | Low — silently `None` |
| `length` | `LENGTH` | Low — silently `None` |

The response envelope is also assumed to be:

```json
{ "data": { "rows": [ { ... } ] } }
```

with a fallback for `{ "rows": [ { ... } ] }`.

---

## How to verify

During initial production testing:

1. **Enable `DEBUG` logging** for the `custom_components.marinetraffic_tracker` logger in `configuration.yaml`:

   ```yaml
   logger:
     default: warning
     logs:
       custom_components.marinetraffic_tracker: debug
   ```

2. **Add a temporary log statement** at the top of `_parse_row` to dump the raw dict:

   ```python
   _LOGGER.debug("Raw vessel row keys: %s", list(row.keys()))
   _LOGGER.debug("Raw vessel row sample: %s", row)
   ```

3. **Restart Home Assistant** and wait for the first poll.

4. **Inspect the logs** for the raw key names and compare against the table above.

5. **If any key name differs**, update `_parse_row` accordingly and remove the temporary log statement.

6. **Remove the "placeholder" comment** from the `_parse_response` docstring once field names are confirmed.

---

## Acceptance criteria

- [ ] All field names in `_parse_row` confirmed against a live MarineTraffic response.
- [ ] Any mismatched key names corrected in `_parse_row`.
- [ ] `"placeholder — verify against live data"` comment removed from the `_parse_response` docstring.
- [ ] A brief note added to the PR / commit confirming which HA version and MarineTraffic endpoint was used for verification.

---

## Notes

- The MarineTraffic live-map endpoint is unofficial (scraped from the public web app) and **may change without notice**. This verification should be repeated after any MarineTraffic site update that causes vessels to disappear.
- If the Enhancement issue (add `draught`/`rate_of_turn`/`beam`) is being worked concurrently, those new field names (`DRAUGHT`, `ROT`, `C`, `D`) should be verified at the same time.

_Originated from the non-blocking items noted in PR #19._
