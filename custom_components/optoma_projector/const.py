"""Constants for the Optoma Projector integration."""
from typing import Final

DOMAIN: Final = "optoma_projector"

# Config keys
CONF_MODEL: Final = "model"
CONF_OPTIMISTIC: Final = "optimistic"

# Default values
DEFAULT_NAME: Final = "Optoma Projector"
DEFAULT_MODEL: Final = "ZK708T"  # UHD 4K Laser
DEFAULT_PORT: Final = 80
DEFAULT_TIMEOUT: Final = 6  # Balanced timeout for HTTP responses
DEFAULT_POWER_TIMEOUT: Final = 12  # Power commands need more time
DEFAULT_SCAN_INTERVAL: Final = 4  # Good balance for UI responsiveness
DEFAULT_TRANSITION_SCAN_INTERVAL: Final = 2  # Fast polling during warming/cooling
DEFAULT_STANDBY_SCAN_INTERVAL: Final = 12  # Slower polling in standby
DEFAULT_RETRIES: Final = 2  # 2 retries is sufficient with good timeout
DEFAULT_RETRY_DELAY: Final = 0.8  # Reasonable delay between retries
DEFAULT_OPTIMISTIC: Final = False
# Minimum delay between commands to projector (prevents request collisions)
MIN_COMMAND_INTERVAL: Final = 0.2  # 200ms is safe for modern projectors

# Telnet fallback settings
CONF_TELNET_FALLBACK: Final = "telnet_fallback"
CONF_PROJECTOR_ID: Final = "projector_id"
DEFAULT_TELNET_FALLBACK: Final = False
DEFAULT_PROJECTOR_ID: Final = 0  # 0 = broadcast to all projectors
TELNET_PORT: Final = 23
TELNET_TIMEOUT: Final = 5
TELNET_COMMAND_DELAY: Final = 0.2  # 200ms between commands

# RS232/Telnet commands (format: ~XXYY Z where XX=projector_id, YY=command, Z=value)
TELNET_CMD_POWER_ON: Final = "~{id:02d}00 1"
TELNET_CMD_POWER_OFF: Final = "~{id:02d}00 0"
TELNET_CMD_POWER_STATUS: Final = "~{id:02d}124 1"

# Telnet power status responses
TELNET_STATUS_STANDBY: Final = 0
TELNET_STATUS_WARMING: Final = 1
TELNET_STATUS_COOLING: Final = 2
TELNET_STATUS_READY: Final = 24  # System ready = ON

# Connection pool settings
CONNECTION_LIMIT: Final = 2  # Max simultaneous connections to projector
CONNECTION_LIMIT_PER_HOST: Final = 1  # Only 1 connection at a time to same host

# API constants
CONTROL_PATH: Final = "/form/control_cgi"
COOKIE: Final = "atop=1"

# Commands
CMD_QUERY: Final = "QueryControl=QueryControl"
CMD_QUERY_INFO: Final = "QueryInfo=QueryInfo"  # Query device info (model, firmware, etc.)
CMD_POWER_ON: Final = "btn_powon=btn_powon"
CMD_POWER_OFF: Final = "btn_powoff=btn_powoff"

# State keys from projector response
KEY_POWER: Final = "pw"
KEY_INPUT_SOURCE: Final = "a"
KEY_VOLUME: Final = "m"
KEY_BRIGHTNESS: Final = "c"
KEY_CONTRAST: Final = "d"
KEY_PICTURE_MODE: Final = "b"

# Power states - Optoma projectors report these values
# 0 = Standby, 1 = On, 2 = Warming Up, 3 = Cooling Down
POWER_STATE_STANDBY: Final = "0"
POWER_STATE_ON: Final = "1"
POWER_STATE_WARMING: Final = "2"
POWER_STATE_COOLING: Final = "3"

POWER_STATES: Final = {
    POWER_STATE_STANDBY: "standby",
    POWER_STATE_ON: "on",
    POWER_STATE_WARMING: "warming",
    POWER_STATE_COOLING: "cooling",
}

# Value returned by projector for "not available" fields
VALUE_NOT_AVAILABLE: Final = "255"

# Lock timeout for async operations (seconds)
LOCK_TIMEOUT: Final = 15  # Increased for slow projector responses

# Switch definitions: (id, name, state_key, command, is_toggle)
SWITCHES: Final = [
    ("av_mute", "AV Mute", "F15", "avmute=avmute", True),
    ("freeze", "Freeze", "F0", "freeze=freeze", True),
    ("info_hide", "Information Hide", "F10", "infohide=infohide", True),
    ("high_altitude", "High Altitude", "O", "altitude=altitude", True),
    ("keypad_lock", "Keypad Lock", "F12", "keypad=keypad", True),
    ("display_mode_lock", "Display Mode Lock", "F11", "dismdlocked=dismdlocked", True),
    ("direct_power_on", "Direct Power On", "F7", "directpwon=directpwon", True),
    ("trigger_12v", "12V Trigger", "F14", "12vtrigger=12vtrigger", True),
    ("signal_power_on", "Signal Power On", "F21", "signalpwon=signalpwon", True),
    ("warping", "Warping", "F22", "warping=warping", True),
    ("sync_3d_invert", "3D Sync Invert", "T", "3Dsync=3Dsync", True),
    ("speaker_enable", "Internal Speaker", "F", "speaker=speaker", True),
    ("mute_audio", "Audio Mute", "j", "mute=mute", True),
    ("dynamic_black", "Dynamic Black", "F18", "dynamic=dynamic", True),
    ("always_on", "Always On", "F13", "alwayson=alwayson", True),
]

# Select definitions: (id, name, state_key, param, options)
SELECTS: Final = [
    (
        "input_source",
        "Input Source",
        "a",
        "source",
        [
            ("0", "HDMI1"),
            ("1", "HDMI2"),
            ("2", "HDBaseT"),
            ("3", "VGA 1"),
            ("4", "VGA 2"),
        ],
    ),
    (
        "audio_input",
        "Audio Input",
        "F6",
        "audio",
        [
            ("0", "Default"),
            ("1", "Audio1"),
            ("2", "Audio2"),
        ],
    ),
    (
        "mode_3d",
        "3D Mode",
        "w",
        "3dmode",
        [
            ("1", "Off"),
            ("2", "On"),
        ],
    ),
    (
        "mode_3d_to_2d",
        "3D to 2D",
        "F17",
        "3dto2d",
        [
            ("0", "3D"),
            ("1", "L"),
            ("2", "R"),
        ],
    ),
    (
        "mode_3d_format",
        "3D Format",
        "E",
        "3dformat",
        [
            ("0", "Auto"),
            ("1", "SBS"),
            ("2", "Top and Bottom"),
            ("3", "Frame Sequential"),
            ("4", "Frame Packing"),
        ],
    ),
    (
        "picture_mode",
        "Picture Mode",
        "b",
        "dismode",
        [
            ("0", "Vivid"),
            ("1", "HDR"),
            ("2", "HLG"),
            ("3", "Cinema"),
            ("4", "Game"),
            ("5", "Golf SIM."),
            ("6", "Reference"),
            ("7", "Bright"),
            ("8", "DICOM SIM."),
            ("9", "3D"),
            ("10", "ISF Day"),
            ("11", "ISF Night"),
            ("12", "ISF 3D"),
        ],
    ),
    (
        "color_space",
        "Color Space",
        "F1",
        "colorsp",
        [
            ("0", "Auto"),
            ("2", "RGB (0~255)"),
            ("3", "RGB (16~235)"),
            ("4", "YUV"),
        ],
    ),
    (
        "gamma",
        "Gamma",
        "C",
        "Degamma",
        [
            ("4", "Film"),
            ("6", "Graphics"),
            ("5", "1.8"),
            ("9", "2.0"),
            ("7", "2.2"),
            ("10", "2.4"),
        ],
    ),
    (
        "color_temperature",
        "Color Temperature",
        "D",
        "colortmp",
        [
            ("0", "Warm"),
            ("1", "Standard"),
            ("2", "Cool"),
            ("3", "Cold"),
        ],
    ),
    (
        "aspect_ratio",
        "Aspect Ratio",
        "L",
        "aspect0",
        [
            ("0", "4:3"),
            ("1", "16:9"),
            ("8", "Full"),
            ("3", "21:9"),
            ("4", "32:9"),
            ("5", "LBX"),
            ("6", "Native"),
            ("7", "Auto"),
        ],
    ),
    # Note: Screen Type (F20) removed - not supported on UHD Laser series
    # The projector returns invalid values (e.g., 19) for this field
    (
        "projection_mode",
        "Projection Mode",
        "t",
        "projection",
        [
            ("0", "Front"),
            ("1", "Front Ceiling"),
            ("2", "Rear"),
            ("3", "Rear Ceiling"),
        ],
    ),
    (
        "background_color",
        "Background Color",
        "F2",
        "background",
        [
            ("0", "None"),
            ("1", "Blue"),
            ("2", "Red"),
            ("3", "Green"),
            ("4", "Grey"),
            ("5", "Logo"),
        ],
    ),
    (
        "wall_color",
        "Wall Color",
        "F3",
        "wall",
        [
            ("0", "Off"),
            ("1", "Blackboard"),
            ("2", "Light Yellow"),
            ("3", "Light Green"),
            ("4", "Light Blue"),
            ("5", "Pink"),
            ("6", "Grey"),
        ],
    ),
    (
        "startup_logo",
        "Startup Logo",
        "o",
        "logo",
        [
            ("0", "Default"),
            ("1", "Neutral"),
            ("6", "Custom Logo"),
        ],
    ),
    (
        "power_mode",
        "Power Mode",
        "F16",
        "pwmode",
        [
            ("1", "Eco"),
            ("0", "Active"),
            ("3", "Active(20min)"),
            ("2", "Communication"),
            ("4", "Communication(20min)"),
        ],
    ),
    (
        "light_source_mode",
        "Light Source Mode",
        "l",
        "lampmd",
        [
            ("1", "Eco"),
            ("2", "Power100"),
            ("3", "Power95"),
            ("4", "Power90"),
            ("5", "Power85"),
            ("6", "Power80"),
            ("7", "Power75"),
            ("8", "Power70"),
            ("9", "Power65"),
            ("10", "Power60"),
            ("11", "Power55"),
            ("12", "Power50"),
        ],
    ),
]

# Number definitions: (id, name, state_key, param, min, max, step, unit)
NUMBERS: Final = [
    ("volume", "Volume", "m", "vol", 0, 100, 1, "%"),
    ("mic_volume", "Mic Volume", "z", "mic", 0, 100, 1, "%"),
    ("brightness", "Brightness", "c", "bright", -50, 50, 1, None),
    ("contrast", "Contrast", "d", "contrast", -50, 50, 1, None),
    ("sharpness", "Sharpness", "f", "Sharp", 1, 15, 1, None),
    ("phase", "Phase", "A", "Phase", -63, 63, 1, None),
    ("brilliant_color", "Brilliant Color", "F4", "brill", 1, 10, 1, None),
    ("zoom_value", "Zoom Value", "r", "zoom", -5, 20, 1, None),
    ("h_keystone", "Horizontal Keystone", "J", "hkeys", -30, 30, 1, None),
    ("v_keystone", "Vertical Keystone", "K", "vkeys", -30, 30, 1, None),
    ("h_shift", "Horizontal Shift", "M", "hpos", -100, 100, 1, None),
    ("v_shift", "Vertical Shift", "N", "vpos", -100, 100, 1, None),
    ("sleep_timer", "Sleep Timer", "F5", "sleep", 0, 990, 30, "min"),
    ("projector_id", "Projector ID", "F8", "projid", 0, 99, 1, None),
    ("remote_code", "Remote Code", "F9", "remote", 0, 99, 1, None),
]

# Button definitions: (id, name, command)
BUTTONS: Final = [
    ("resync", "Resync", "resync=resync"),
    ("reset", "Reset", "reset=reset"),
    ("logo_capture", "Logo Capture", "logocapture=logocapture"),
    ("corner_reset", "Four Corners Reset", "cornerreset=cornerreset"),
]
