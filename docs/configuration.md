# Configuration Guide

This guide walks you through every option available in the Norwegian Maritime Tracker setup wizard and options flow.

---

## 1. Obtaining BarentsWatch Credentials

The integration uses the official [BarentsWatch AIS API](https://www.barentswatch.no/bwapi/) which is **free** to use.

1. Create an account at <https://www.barentswatch.no/mine-side/>.
2. Log in and navigate to **My profile → API access**.
3. Register a new application / client.  Give it a descriptive name such as `home-assistant-ais`.
4. Copy the generated **Client ID** and **Client Secret** — you will paste these into the integration wizard.

> **Keep your credentials safe.** Treat the Client Secret like a password; do not share it publicly.

---

## 2. Config Flow Walkthrough

The setup wizard runs in four steps.

### Step 1 — Tracking mode

Choose how the integration defines the area it monitors.

| Option | Description |
|---|---|
| **Radius** | Pick a centre point on an interactive map and specify a radius in kilometres.  Easiest to set up. |
| **Bounding box** | Enter explicit north / south / east / west degree values.  Useful for irregular coastlines. |

### Step 2 — Area selection

#### Radius mode

An interactive map selector appears.  Drop a pin on your location of interest, then set the **Radius (km)** slider.  The default radius is **50 km**.

#### Bounding box mode

Enter four decimal-degree values:

| Field | Description |
|---|---|
| **North** | Northernmost latitude (e.g. `60.5`) |
| **South** | Southernmost latitude (e.g. `59.5`) |
| **East** | Easternmost longitude (e.g. `5.5`) |
| **West** | Westernmost longitude (e.g. `4.5`) |

> **Tip:** Use [bboxfinder.com](http://bboxfinder.com/) to draw your box visually and read off the coordinates.

### Step 3 — BarentsWatch credentials

Enter the **Client ID** and **Client Secret** you obtained in step 1.

### Step 4 — Update settings and filters

| Field | Default | Description |
|---|---|---|
| **Update interval (s)** | 60 | How often (in seconds) the integration polls the API.  Minimum is **5 s** for the Kystverket source.  Lower values increase data freshness but raise API load. |
| **Stale timeout (s)** | 3600 | Vessels not seen for longer than this duration are removed from the live map. |
| **Vessel type filter** | *(all)* | Optionally limit tracking to specific AIS vessel categories (Cargo, Tanker, Passenger, Fishing, etc.).  Leave empty to track all types. |
| **Exclude anchored / moored vessels** | Off | When enabled, vessels with AIS status *At Anchor* or *Moored* are hidden from the live map and device trackers. |

---

## 3. Radius vs Bounding Box

| | Radius | Bounding box |
|---|---|---|
| **Ease of setup** | ✅ Interactive map picker | ⚠️ Manual coordinate entry |
| **Shape** | Circular | Rectangular |
| **Good for** | Harbours, a single port, local monitoring | Fjords, straits, or areas that span a long distance in one direction |
| **Efficiency** | Fewer false positives at the edges | Can include unwanted land area |

---

## 4. Update Interval Recommendations

- **60 s** — good default for most home monitoring use cases.
- **30 s** — a good choice near a busy port.
- **5 s** — maximum rate for the Kystverket API; only use if you need near-real-time tracking for automations.

> Avoid polling more often than needed.  The BarentsWatch API is a shared public resource.

---

## 5. Vessel Type Filter

The filter uses AIS ship-type codes.  If you only want to see cargo vessels and tankers, select **Cargo** and **Tanker**.  All other vessel types will be ignored.

Common categories:

| Label | AIS type codes |
|---|---|
| Fishing | 30 |
| Towing | 31 |
| Sailing | 36 |
| Pleasure Craft | 37 |
| Pilot Vessel | 50 |
| Search and Rescue | 51 |
| Tug | 52 |
| Passenger | 60–64, 69 |
| Cargo | 70–74, 79 |
| Tanker | 80–84, 89 |
| Other | 90–94, 99 |

---

## 6. Anchored / Moored Vessel Exclusion

When **Exclude anchored / moored vessels** is enabled:

- Vessels whose AIS navigational status is `At Anchor` or `Moored` are excluded from device trackers and the vessel-count sensor.
- A separate **anchored vessel count** sensor and **anchored vessels** attribute are still updated so you can track how many vessels are sitting still.
- Re-enabling the option (setting it to *Off*) immediately re-includes those vessels on the next update.

This option is particularly useful if your monitored area is a port where many vessels anchor for long periods and you only want to track active, moving traffic.

---

## 7. Changing Settings After Setup

Options can be changed without re-adding the integration:

1. Go to **Settings → Devices & Services**.
2. Find **Norwegian Maritime Tracker** and click **Configure**.
3. Adjust the options and click **Submit**.

Changes take effect on the next API poll.
