DOMAIN = "caso_winecooler"

API_BASE = "https://publickitchenapi.casoapp.com/api/v1.2"

CONF_API_KEY = "api_key"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 600  # 10 minutes
MIN_SCAN_INTERVAL = 60       # 1 minute minimum to stay within rate limits

PLATFORMS = ["sensor", "light", "binary_sensor"]
