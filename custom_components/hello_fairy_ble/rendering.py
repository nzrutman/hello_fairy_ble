"""Small deterministic notification rendering (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

from .pixel_protocol import validate_color_byte

# A self-authored 3×5 font, avoiding bundled vendor art or external font files.
_ROWS = {
    "A": "010101111101101",
    "B": "110101110101110",
    "C": "011100100100011",
    "D": "110101101101110",
    "E": "111100110100111",
    "F": "111100110100100",
    "G": "011100101101011",
    "H": "101101111101101",
    "I": "111010010010111",
    "J": "001001001101010",
    "K": "101101110101101",
    "L": "100100100100111",
    "M": "101111111101101",
    "N": "101111111111101",
    "O": "010101101101010",
    "P": "110101110100100",
    "Q": "010101101111011",
    "R": "110101110101101",
    "S": "011100010001110",
    "T": "111010010010010",
    "U": "101101101101111",
    "V": "101101101101010",
    "W": "101101111111101",
    "X": "101101010101101",
    "Y": "101101010010010",
    "Z": "111001010100111",
    "0": "111101101101111",
    "1": "010110010010111",
    "2": "110001010100111",
    "3": "110001010001110",
    "4": "101101111001001",
    "5": "111100110001110",
    "6": "011100110101010",
    "7": "111001010010010",
    "8": "010101010101010",
    "9": "010101011001110",
    " ": "000000000000000",
    ":": "000010000010000",
    "-": "000000111000000",
    ".": "000000000000010",
    "!": "010010010000010",
    "?": "110001010000010",
}
_ICONS = {
    "heart": ["01010", "11111", "11111", "01110", "00100"],
    "bell": ["00100", "01110", "01110", "11111", "00100"],
    "door": ["11111", "10001", "10011", "10001", "11111"],
}


def render_pages(text, width=20, color_byte=0, background_byte=254, icon="none"):
    """Render centered pages; unsupported characters fail before any radio command."""
    validate_color_byte(color_byte)
    validate_color_byte(background_byte)
    if type(width) is not int or width not in range(20, 161, 20):
        raise ValueError("Choose one to eight curtains")
    if not isinstance(text, str) or len(text) > 160 or not text and icon == "none":
        raise ValueError("Enter 1–160 characters or choose a notification icon")
    text = text.upper()
    if any(c not in _ROWS for c in text):
        raise ValueError("Use letters A–Z, digits, spaces, colon, dash, period, ! or ?")
    if icon not in ("none", *_ICONS):
        raise ValueError("Choose none, bell, heart or door")
    columns = (width + 1) // 4
    pages = []
    for start in range(0, max(1, len(text)), columns):
        line = text[start : start + columns]
        frame = [background_byte] * (width * 20)
        left = (width - (len(line) * 4 - 1)) // 2
        top = 10 if icon != "none" else 7
        for pos, char in enumerate(line):
            for pixel, bit in enumerate(_ROWS[char]):
                if bit == "1":
                    frame[(top + pixel // 3) * width + left + pos * 4 + pixel % 3] = color_byte
        if icon != "none":
            top_icon = 7 if not text else 2
            for y, row in enumerate(_ICONS[icon]):
                for x, bit in enumerate(row):
                    if bit == "1":
                        frame[(y + top_icon) * width + (width - 5) // 2 + x] = color_byte
        pages.append(frame)
    return pages


def render_clock(now, width=20, clock_format="24h", color_byte=0, background_byte=254):
    """Render minute precision, with 12h mode using 1–12 without an AM/PM suffix."""
    if clock_format not in ("24h", "12h"):
        raise ValueError("Clock format must be 24h or 12h")
    hour = now.hour if clock_format == "24h" else now.hour % 12 or 12
    return render_pages(f"{hour:02d}:{now.minute:02d}", width, color_byte, background_byte)[0]
