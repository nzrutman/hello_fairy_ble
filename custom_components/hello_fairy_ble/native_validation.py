"""Native action validation before radio access.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import voluptuous as vol


def integer(low, high):
    def validate(value):
        if type(value) is not int or not low <= value <= high:
            raise vol.Invalid(f"expected an integer {low}..{high}")
        return value

    return validate


def weekdays(value):
    days = vol.Schema([integer(1, 7)])(value)
    if len(days) > 7 or len(set(days)) != len(days):
        raise vol.Invalid("weekdays must contain unique days 1..7")
    return days


SCHEMAS = {
    "inspect": vol.Schema({}),
    "music": vol.Schema(
        {
            vol.Required("mode"): integer(1, 4),
            vol.Optional("auto_color", default=True): bool,
            vol.Optional("sensitivity", default=50): integer(1, 100),
            vol.Optional("brightness", default=100): integer(1, 100),
            vol.Optional("hue", default=0): integer(0, 360),
            vol.Optional("saturation", default=100): integer(0, 100),
        }
    ),
    "scene_speed": vol.Schema({vol.Required("speed"): integer(0, 100)}),
    "clock_sync": vol.Schema({}),
    "countdown": vol.Schema(
        {vol.Required("seconds"): integer(0, 86400), vol.Required("power"): bool}
    ),
    "timer": vol.Schema(
        {
            vol.Required("slot"): integer(0, 7),
            vol.Required("hour"): integer(0, 23),
            vol.Required("minute"): integer(0, 59),
            vol.Required("power"): bool,
            vol.Required("enabled"): bool,
            vol.Required("weekdays"): weekdays,
        }
    ),
}
