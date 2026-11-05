# Optoma Projector

[![Marketplace](https://img.shields.io/badge/Marketplace-Available-blue.svg)](https://www.home-assistant.io/integrations/marketplace/)
[![Release](https://img.shields.io/github/v/release/speedy3wk/ha-optoma-projector.svg)](https://github.com/speedy3wk/ha-optoma-projector/releases)
[![Built with AI](https://img.shields.io/badge/Built%20with-AI-blue.svg)](https://github.com/features/copilot)

Home Assistant control for Optoma projectors that expose the web control interface. Created with AI. Fully tested on Optoma ZK708T.

Requires Home Assistant 2026.10 or newer.

## Highlights

- Power, source, volume, mute
- Picture, 3D, geometry, and audio settings
- Diagnostics (hours, power state, last update)
- Media Player entity plus dedicated switches, selects, numbers, and buttons

## Installation

### Marketplace (recommended, Home Assistant 2026.11+)

Since Home Assistant 2026.11, HACS is built in as the [Marketplace](https://www.home-assistant.io/integrations/marketplace/). No separate HACS installation is needed.

1. Open **Settings → Marketplace** as an administrator and accept the community-content warning if prompted.
2. Search for **Optoma Projector**, open its page and select **Install**.
3. Follow the integration setup flow described under **Configuration** below. If it does not open, add the integration under **Settings → Devices & Services**. Restart only if the Marketplace requests it.

If the integration is not listed, select **Add from link** in the Marketplace, enter `https://github.com/speedy3wk/ha-optoma-projector` and select **Add**. Connect GitHub if prompted, then install it from its repository page.

Existing HACS installations migrate automatically when updating to Home Assistant 2026.11; installed integrations and their update entities are kept. Integration updates still require a Home Assistant restart.

### HACS (Home Assistant versions before 2026.11)

For older supported Home Assistant versions, use the following legacy HACS instructions.

Optoma Projector is included in the HACS default repository list. No custom repository is needed.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=speedy3wk&repository=ha-optoma-projector&category=integration)

1. Open HACS and search for **Optoma Projector**, or use the button above.
2. Download the integration and restart Home Assistant.
3. Add the integration under **Settings → Devices & Services** as described below.

HACS must already be installed. The integration requires Home Assistant 2026.10 or newer.

### Manual

1. Copy `custom_components/optoma_projector` into your Home Assistant `config/custom_components/`
2. Restart Home Assistant

## Configuration

1. Settings → Devices & Services → Add Integration
2. Search for "Optoma Projector"
3. Enter the projector IP address

## Options

- Polling interval (seconds)
- Optimistic mode for UI updates
- Telnet fallback for power commands and power state (requires projector Telnet enabled)
- Projector ID (RS232/Telnet ID 0-99)

Behavior notes:
- Polling: 4s default, 2s warming/cooling, 12s standby
- After every command, a short refresh runs (~1s)
- Entities become unavailable after 3 consecutive failed polls
- With Telnet fallback enabled, the power state is read via Telnet when the web interface does not answer (e.g. deep standby), so the projector can still be switched on

## Entities

Primary:
- Media Player: power, source, volume, mute
- Power switch, input source select, volume number

Configuration (examples):
- Picture mode, aspect ratio, color temperature
- Brightness, contrast, zoom, keystone, shift

Diagnostics:
- Light source hours, filter hours, power state, last update (disabled by default)
- Hour sensors are unavailable if the projector does not report them

## Supported Models and Notes

- Tested with Optoma ZK708T (UHD 4K Laser)
- Should work with any Optoma projector that exposes `/form/control_cgi` on port 80
- Not supported: newer models whose web interface only runs via HTTPS on port 8088. The setup dialog reports these as unsupported.
- Some settings return `255` when not available for a specific model
- Deep standby can require Telnet fallback for power commands

## Power State Handling

- Standby, On, Warming, Cooling are reported by the projector
- Power commands are blocked during warming/cooling
- No artificial timers are used

## Troubleshooting

Cannot connect:
- Confirm the projector is on and reachable
- Open `http://<projector-ip>/index_login.asp`
- Check port 80 is not blocked
- "Unsupported model": the projector uses the newer HTTPS web interface (port 8088), which this integration cannot control

Entities unavailable:
- Most configuration entities are unavailable in standby
- Some values return `255` meaning "not available"

Slow response:
- The web UI can be slow; this integration throttles and serializes requests

## Protocol Notes

Requests are HTTP POST to `/form/control_cgi` with `Cookie: atop=1`. Responses are a non-standard JSON format (unquoted keys) that is normalized internally.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/ruff check custom_components tests
.venv/bin/pytest
```

## License

MIT License