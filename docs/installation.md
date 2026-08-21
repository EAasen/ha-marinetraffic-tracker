# Installation Guide

This guide covers installing the Norwegian Maritime Tracker integration into Home Assistant.

## Prerequisites

- Home Assistant 2024.1 or later
- Internet access from your Home Assistant instance
- Free [BarentsWatch](https://www.barentswatch.no/en/) account with API credentials (see [Configuration Guide](configuration.md))

---

## Installing via HACS (Recommended)

[HACS](https://hacs.xyz/) is the Home Assistant Community Store and provides the easiest way to install and update this integration.

1. Open HACS in your Home Assistant sidebar.
2. Click the **⋮ (three-dot menu)** in the top-right corner and choose **Custom repositories**.
3. Paste `https://github.com/EAasen/ha-marinetraffic-tracker` in the **Repository** field, select **Integration** as the category, and click **Add**.
4. Search for **Norwegian Maritime Tracker** in HACS and click **Download**.
5. **Restart Home Assistant** (Settings → System → Restart).
6. After restart, add the integration:
   - Go to **Settings → Devices & Services → Add Integration**.
   - Search for **Norwegian Maritime Tracker** and follow the setup wizard.

---

## Manual Installation

Use this method if you do not have HACS installed.

1. Download the latest release from the [Releases page](https://github.com/EAasen/ha-marinetraffic-tracker/releases).
2. Unzip the archive and locate the `custom_components/marinetraffic_tracker` directory.
3. Copy the entire `marinetraffic_tracker` folder into `/config/custom_components/` on your Home Assistant instance.
   - Your final path should look like `/config/custom_components/marinetraffic_tracker/`.
4. **Restart Home Assistant** (Settings → System → Restart).
5. After restart, add the integration:
   - Go to **Settings → Devices & Services → Add Integration**.
   - Search for **Norwegian Maritime Tracker** and follow the setup wizard.

---

## Verifying the Installation

After adding the integration, navigate to **Settings → Devices & Services**. You should see a new device and several entities (sensors and device trackers) appearing as vessels are detected in your configured area.

---

## Troubleshooting Installation Issues

| Symptom | Possible Cause | Fix |
|---|---|---|
| Integration not found in UI | Files not in the correct path | Verify `/config/custom_components/marinetraffic_tracker/__init__.py` exists |
| Integration not found in UI | Home Assistant not restarted | Restart Home Assistant fully |
| Setup wizard fails immediately | Missing or wrong BarentsWatch credentials | Double-check your Client ID and Secret |
| No entities created after setup | Area contains no AIS traffic | Increase radius or move bounding box |

For more issues see the [Troubleshooting Guide](troubleshooting.md).
