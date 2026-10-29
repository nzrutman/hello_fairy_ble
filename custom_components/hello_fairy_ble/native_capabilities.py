"""Conservative APK capability decoding; unknown extension tags stop parsing.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""


def decode_extensions(data: bytes) -> dict:
    """GetDeviceInfoCmd's counted, variable-width extension list.

    Unknown fields have no length marker, so skipping them would invent later
    capabilities. Truncation invalidates the entire extension list.
    """
    if (
        len(data) < 32
        or data[:2] != b"\xaa\x00"
        or data[2] != len(data) - 4
        or sum(data[:-1]) & 255 != data[-1]
    ):
        return {}
    p = data[3:-1]
    result = {}
    position = 28
    widths = {1: 1, 2: 0, 3: 1, 4: 2, 7: 0, 8: 1, 9: 6, 10: 13, 12: 1, 13: 1, 14: 1}
    for _ in range(p[27]):
        if position >= len(p):
            return {}
        tag = p[position]
        position += 1
        if tag == 11:
            if position >= len(p):
                return {}
            width = 1 + p[position]
        elif tag in widths:
            width = widths[tag]
        else:
            return {}  # Fail closed: unknown tag length means no reliable list.
        if position + width > len(p):
            return {}
        value = p[position : position + width]
        if tag == 2:
            result["scene_loop_advertised"] = True
        elif tag == 8:
            result["music_mode"] = value[0]
        elif tag == 13:
            result["collection_slots_advertised"] = value[0]
        position += width
    if position != len(p):
        return {}
    return result


def is_researched_profile(info: dict | None) -> bool:
    """New native controls remain restricted to the recorded model/firmware."""
    return info is not None and tuple(
        info.get(k) for k in ("model", "firmware", "led_count", "columns", "rows", "diy_type")
    ) == ("25025", "4.6.0", 400, 20, 20, 3)
