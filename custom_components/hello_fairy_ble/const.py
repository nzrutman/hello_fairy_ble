DOMAIN = "hello_fairy_ble"
DISCOVERY_NAMES = ("Hello Fairy-",)

# Hello Fairy BLE Service and Characteristic UUIDs from fairy.yaml
SERVICE_UUID = "49535343-fe7d-4ae5-8fa9-9fafd205e455"
COMMAND_CHARACTERISTIC_UUID = "49535343-8841-43f4-a8d4-ecbe34729bb3"
NOTIFY_CHARACTERISTIC_UUID = "49535343-1E4D-4BD9-BA61-23C647249616"

# Hello Fairy command structure constants
CMD_PREFIX = 0xAA
CMD_POWER = 0x02
CMD_COLOR_PRESET = 0x03
MODE_COLOR = 0x01
MODE_PRESET = 0x02

ACK2 = [0xAA, 0x02, 0x00, 0xAC]
ACK3 = [0xAA, 0x03, 0x00, 0xAD]

# Preset effects mapping
EFFECT_PRESETS = {
    "Blue White Dissolve": 41,
    "Blue Sparkle": 56,
    "White Sparkle": 57,
    "Blue with Pink Sparkle": 8,
    "Fireworks": 17,
    "Xmas": 18,
    "Candy Cane": 50,
    "Halloween": 20,
    "Red Gold": 40,
    "July 4th": 39,
    "Valentine": 46,
    "St. Patrick": 47,
    "May Day": 48,
    "Snow Day": 54,
}
