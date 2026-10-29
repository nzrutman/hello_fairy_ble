"""Read-only native font capability framing found in the official Android app.

This module deliberately provides no native text upload or storage commands:
the captured curtain has not reported which font protocol it supports.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from .pixel_protocol import build_packet


def build_text_capability_query() -> bytes:
    """Build the empty DD query sent when Android opens its curtain text list.

    Cmds.Set_Text_UniCode_Data() has cmdS=-1, so it writes no payload.
    This does not select a mode, upload characters, or modify stored designs.
    """
    return build_packet(0xDD, [])


def decode_text_capability(data: bytes) -> dict | None:
    """Accept only a checksum-valid, exactly one-byte DD response.

    Android accepts a positive version as custom font support, and version >=2
    as border support. A zero response does not establish ASCII compatibility.
    None represents an unrelated, malformed, or absent response; never infer
    support from an ACK or a timeout.
    """
    if (
        not isinstance(data, bytes | bytearray)
        or len(data) != 5
        or data[:3] != b"\xaa\xdd\x01"
        or sum(data[:-1]) & 255 != data[-1]
    ):
        return None
    version = data[3]
    return {
        "source": "device_notification",
        "font_protocol_version": version,
        "custom_font_reported": version >= 1,
        "font_border_reported": version >= 2,
        "native_text_upload_verified": False,
    }
