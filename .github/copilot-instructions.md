# Copilot Instructions for Optoma Projector Integration

## Project Overview

This is a **Home Assistant custom integration** for Optoma UHD Laser projectors using their HTTP web control API. It's a HACS-compatible integration following modern Home Assistant patterns (2024+).

## Architecture

### Core Components

- **`coordinator.py`** - Central `DataUpdateCoordinator` that manages HTTP communication, polling, and state. All entities share this coordinator.
- **`entity.py`** - Base `OptomaEntity` class extending `CoordinatorEntity` with shared device info and translation key patterns.
- **`const.py`** - All entity definitions (`SWITCHES`, `SELECTS`, `NUMBERS`, `BUTTONS`) as tuples defining state keys, commands, and options.
- **`__init__.py`** - Entry setup using `runtime_data` pattern (not `hass.data`).

### Data Flow

1. Coordinator polls projector via HTTP POST to `/form/control_cgi`
2. Response is non-standard JSON with unquoted keys (e.g., `{pw:"0",a:"1"}`)
3. `_parse_response()` fixes JSON, stores in coordinator data
4. Entities read from coordinator data using state keys from `const.py`

### Entity Pattern

All entities follow a declarative pattern - definitions in `const.py` are converted to `EntityDescription` dataclasses:

```python
# const.py - Define entities as tuples
SWITCHES: Final = [
    ("av_mute", "AV Mute", "F15", "avmute=avmute", True),
    #  id,       name,     state_key, command,    is_toggle
]

# switch.py - Build descriptions from const
SWITCH_DESCRIPTIONS = tuple(
    OptomaSwitchEntityDescription(
        key=switch_id,
        translation_key=switch_id,  # Maps to strings.json
        state_key=state_key,
        command=command,
    )
    for switch_id, _name, state_key, command, _is_toggle in SWITCHES
)
```

## Key Conventions

### Adding New Entities

1. Add tuple to `const.py` (`SWITCHES`, `SELECTS`, `NUMBERS`, or `BUTTONS`)
2. Add translation in `strings.json` under `entity.<platform>.<key>`
3. Copy translations to `translations/en.json` and `translations/de.json`
4. Entity is automatically created - no code changes needed in platform files

### Translation Keys

Use `translation_key` attribute, not hardcoded names:
```python
self._attr_translation_key = key  # Matches strings.json path
self._attr_has_entity_name = True  # Required for translation_key
```

### Availability Pattern

Most entities are only available when projector is on:
```python
@property
def available(self) -> bool:
    return self.coordinator.last_update_success and self.coordinator.is_on
```

### Special Values

- `VALUE_NOT_AVAILABLE = "255"` - Projector returns this for unsupported fields
- Power states: `0`=standby, `1`=on, `2`=warming, `3`=cooling

## HTTP Protocol Details

- Endpoint: `POST /form/control_cgi`
- Headers: `Content-Type: application/x-www-form-urlencoded`, `Cookie: atop=1`
- Commands: `QueryControl=QueryControl` (poll), `btn_powon=btn_powon` (power on)
- Session can expire randomly - coordinator auto-recreates on login redirect

## Concurrency

- `PARALLEL_UPDATES = 1` on all platforms - projector handles one request at a time
- `asyncio.Lock` in coordinator prevents request collisions
- `LOCK_TIMEOUT = 10` prevents deadlocks

## Testing

No test framework is currently set up. Test manually against real projector hardware by:
1. Copy to Home Assistant `config/custom_components/`
2. Restart Home Assistant
3. Add integration via Settings → Devices & Services

## Files to Update Together

When modifying entity definitions:
- `const.py` - Entity tuple definitions
- `strings.json` - UI strings (source of truth)
- `translations/en.json` - English translations (copy from strings.json)
- `translations/de.json` - German translations
