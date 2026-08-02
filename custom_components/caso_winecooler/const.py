DOMAIN = "caso_winecooler"

API_BASE = "https://publickitchenapi.casoapp.com/api/v1.3"

CONF_API_KEY = "api_key"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_SCAN_INTERVAL = "scan_interval"

# Device categories. The API has no type field on GetDevices, so the type is
# detected once during the config flow (see config_flow._detect_device_type)
# and stored on the entry. Existing entries created before this existed default
# to wine cooler.
DEVICE_TYPE_WINE = "winecooler"
DEVICE_TYPE_BBQ = "bbqcooler"

DEFAULT_SCAN_INTERVAL = 600  # 10 minutes
MIN_SCAN_INTERVAL = 60       # 1 minute minimum to stay within rate limits

PLATFORMS = ["sensor", "light", "binary_sensor"]
