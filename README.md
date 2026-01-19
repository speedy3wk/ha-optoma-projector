# Optoma Projector Integration for Home Assistant

Native Home Assistant integration for Optoma UHD Laser projectors with web control interface.

## Features

- **Power Control** - Turn projector on/off
- **Input Source** - HDMI1, HDMI2, HDBaseT, VGA
- **Picture Settings** - Picture mode, brightness, contrast, color temperature
- **Audio** - Volume, mute, audio input selection
- **3D Settings** - 3D mode, format, sync invert
- **Geometry** - Keystone, zoom, shift
- **Diagnostics** - Light source hours, filter hours, power state, last update
- **Media Player** - Main entity with power, source, volume, mute
- **Actions** - Buttons like resync, reset, logo capture

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots menu → "Custom repositories"
4. Add this repository URL and select "Integration":
	- https://github.com/speedy3wk/ha-optoma-projector
5. Search for "Optoma Projector" and install
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/optoma_projector` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Optoma Projector"
4. Enter the IP address of your projector
5. Click Submit

## Options

After setup, you can configure:
- **Polling interval** (seconds)
- **Optimistic mode** (instant UI updates while commands are in flight)
- **Telnet fallback** for power commands (requires projector Telnet enabled)
- **Projector ID** (RS232/Telnet ID 0–99)

## Entities

### Primary Controls (shown on device page)

- **Projector** (Media Player): Power, source, volume, mute
- **Power** (Switch): Main power control
- **Input Source** (Select): HDMI1, HDMI2, HDBaseT, VGA
- **Volume** (Number): 0-100%

### Configuration Entities

- **Picture Mode** (Select): Vivid, HDR, Cinema, Game, etc.
- **Aspect Ratio** (Select): 4:3, 16:9, 21:9, etc.
- **Color Temperature** (Select): Warm, Standard, Cool, Cold
- **Brightness** (Number): -50 to +50
- **Contrast** (Number): -50 to +50
- **…and many more**

### Diagnostic Entities

- **Light Source Hours** (Sensor): Total operating hours
- **Filter Hours** (Sensor): Filter operating hours
- **Power State** (Sensor): Standby / On / Warming / Cooling
- **Last Update** (Sensor): Last successful poll timestamp

## Supported Models

Tested with:
- Optoma ZK708T (UHD 4K Laser)

Should work with any Optoma projector that has the web control interface at `/form/control_cgi`.

## Power State Handling
The integration properly handles all projector power states:
- **Standby** - Projector is off
- **On** - Projector is running
- **Warming** - Projector is starting up (power commands blocked)
- **Cooling** - Projector is shutting down (power commands blocked)

The integration relies on the projector's reported state - no artificial timers needed. Laser projectors like the ZK708T can restart immediately once they report being ready.

## Troubleshooting

### Cannot Connect

1. Ensure the projector is powered on and connected to the network
2. Try accessing `http://<projector-ip>/index_login.asp` in a browser
3. Check that no firewall is blocking port 80

### Session Expired / Login Issues

The projector's web interface can randomly expire sessions. The integration automatically:
- Detects redirects to login pages
- Recreates the HTTP session when needed
- Retries failed commands

### Entities Unavailable / Unknown

Most configuration entities (selects, numbers, switches, buttons) are marked **unavailable** when:
- The projector is in standby mode (most settings are not reported)
- The field returns `255` which means "not available" for this projector model

Some diagnostic sensors can show **unknown** when the projector does not report a value.

The Power switch is always available.

### Slow Response

The projector's web interface can be slow. The integration uses:
- 4 second polling interval (2 seconds during warming/cooling, 12 seconds in standby)
- 6 second timeout with retries (12 seconds for power commands)
- Request throttling (200ms minimum between commands)
- Request queueing with locks to prevent collisions

## Technical Details

### Protocol
The integration communicates via HTTP POST to `/form/control_cgi` with:
- Content-Type: `application/x-www-form-urlencoded`
- Cookie: `atop=1`

### Response Format
The projector returns a non-standard JSON format with unquoted keys:
```
{pw:"0",a:"1",b:"255",c:"0",...}
```
This is automatically converted to valid JSON.

### Power States
| Value | State | Description |
|-------|-------|-------------|
| 0 | Standby | Projector is off |
| 1 | On | Projector is running |
| 2 | Warming | Starting up (commands blocked) |
| 3 | Cooling | Shutting down (commands blocked) |

## Development

This integration was created with AI tools and reviewed/edited by humans.

## License

MIT License

## Credits

Based on analysis of the Optoma web control protocol.
This integration was completely generated with AI tools and reviewed/edited by humans.
