# Troubleshooting Guide

This guide covers the most common problems encountered when installing and using Norwegian Maritime Tracker.

---

## Enabling Debug Logs

Before reporting an issue or digging deeper, enable debug logging for the integration.  Add the following to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.marinetraffic_tracker: debug
```

Restart Home Assistant, reproduce the problem, and then check the logs:

- **Settings → System → Logs** — view the log in the UI.
- Or examine the file at `/config/home-assistant.log`.

---

## Common Issues

### Integration not found after installation

**Symptom:** The integration does not appear when searching in **Settings → Devices & Services → Add Integration**.

**Causes and fixes:**

1. **Files are not in the correct location.**  
   Verify the directory `/config/custom_components/marinetraffic_tracker/` exists and contains `__init__.py`, `manifest.json`, and other Python files.
2. **Home Assistant was not restarted.**  
   A full restart (not just a configuration reload) is required after adding a new custom component.
3. **HACS download did not complete.**  
   In HACS, check the download history.  If it shows an error, retry the download.

---

### Setup wizard fails — credential error

**Symptom:** The wizard shows "Invalid credentials" or "Authentication failed".

**Fixes:**

1. Copy the **Client ID** and **Client Secret** again directly from the BarentsWatch portal — trailing whitespace is a common cause.
2. Verify your BarentsWatch application has the **AIS** API permission enabled.
3. Try logging into <https://www.barentswatch.no/bwapi/> with the credentials to confirm they work.

---

### No vessels appear after setup

**Symptom:** The integration is set up and polling succeeds, but the vessel count stays at 0.

**Causes and fixes:**

1. **Area has no traffic.**  The monitored radius or bounding box may be in an area with little AIS activity.  Try increasing the radius or choosing a busier waterway.
2. **Vessel type filter is too restrictive.**  If you have enabled a filter, verify it matches the vessel types actually present in the area.
3. **Anchored vessels are excluded.**  If *Exclude anchored / moored vessels* is enabled and all vessels in the area are anchored, the active count will be 0 even though anchored vessels are still recorded.
4. **Stale timeout is very short.**  If the timeout is set to less than one polling interval, vessels expire before the next update.

---

### Vessels disappear unexpectedly

**Symptom:** Vessels that were visible stop appearing.

**Causes and fixes:**

1. **Stale timeout reached.**  Vessels not seen for longer than the configured stale timeout are removed.  Increase the stale timeout in the integration options.
2. **Vessel left the area.**  AIS transponders only broadcast while powered.  A vessel that has docked, switched off its transponder, or left your area will stop appearing.
3. **API rate limiting.**  If you are polling very frequently, BarentsWatch may throttle responses.  Increase the update interval.

---

### API credential validation

To verify your credentials manually, run the following cURL command from a terminal or the Home Assistant SSH add-on:

```bash
curl -X POST "https://id.barentswatch.no/connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials&scope=ais"
```

A successful response looks like:

```json
{"access_token": "...", "token_type": "Bearer", "expires_in": 3600}
```

An error response indicates incorrect credentials or missing scope.

---

### High memory usage

**Symptom:** Home Assistant memory increases noticeably after installing the integration.

**Causes and fixes:**

1. **Position history is large.**  Each vessel stores up to 20 position history points.  If thousands of vessels pass through your area over time this is normal.
2. **Stale timeout is very long.**  Lower the stale timeout so vessels are evicted from memory sooner.

---

### Connection testing

Use the Home Assistant network tools or the SSH add-on to test connectivity to the BarentsWatch API:

```bash
curl -I "https://live.ais.barentswatch.no/v1/combined"
```

You should receive an HTTP 401 (Unauthorized) which confirms the endpoint is reachable.  An HTTP connection error or timeout indicates a network problem between Home Assistant and the internet.

---

## Reporting Issues

If none of the above solutions resolve your problem:

1. Collect the debug logs (see *Enabling Debug Logs* above).
2. Note your Home Assistant version, integration version, and configuration options.
3. Open an issue at <https://github.com/EAasen/ha-marinetraffic-tracker/issues> with:
   - A clear description of the problem.
   - Steps to reproduce.
   - Relevant log excerpts (redact your credentials).
