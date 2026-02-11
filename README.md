# Optoma Projector

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/speedy3wk/ha-optoma-projector.svg)](https://github.com/speedy3wk/ha-optoma-projector/releases)
[![Built with AI](https://img.shields.io/badge/Built%20with-AI-blue.svg)](https://github.com/features/copilot)

Home Assistant control for Optoma projectors that expose the web control interface. Created with AI. Fully tested on Optoma ZK708T.

## Highlights

- Power, source, volume, mute
- Picture, 3D, geometry, and audio settings
- Diagnostics (hours, power state, last update)
- Media Player entity plus dedicated switches, selects, numbers, and buttons

## Installation

### HACS

1. HACS → Integrations → menu → Custom repositories
2. Add: https://github.com/speedy3wk/ha-optoma-projector (Integration)
3. Install "Optoma Projector"
4. Restart Home Assistant

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
- Telnet fallback for power commands (requires projector Telnet enabled)
- Projector ID (RS232/Telnet ID 0-99)

Behavior notes:
- Polling: 4s default, 2s warming/cooling, 12s standby
- After toggles, a short refresh runs (~0.8s)

## Entities

Primary:
- Media Player: power, source, volume, mute
- Power switch, input source select, volume number

Configuration (examples):
- Picture mode, aspect ratio, color temperature
- Brightness, contrast, zoom, keystone, shift

Diagnostics:
- Light source hours, filter hours, power state, last update

## Supported Models and Notes

- Tested with Optoma ZK708T (UHD 4K Laser)
- Should work with any Optoma projector that exposes `/form/control_cgi`
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

Entities unavailable:
- Most configuration entities are unavailable in standby
- Some values return `255` meaning "not available"

Slow response:
- The web UI can be slow; this integration throttles and serializes requests

## Protocol Notes

Requests are HTTP POST to `/form/control_cgi` with `Cookie: atop=1`. Responses are a non-standard JSON format (unquoted keys) that is normalized internally.

## License

MIT License