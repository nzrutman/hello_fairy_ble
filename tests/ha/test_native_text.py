"""Native font capability responses never authorize unverified text uploads.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import pytest

from custom_components.hello_fairy_ble.native_text import (
    build_text_capability_query,
    decode_text_capability,
)
from custom_components.hello_fairy_ble.pixel_protocol import build_packet


def test_native_font_query_is_read_only_empty_payload():
    assert build_text_capability_query() == bytes.fromhex("aadd0087")


@pytest.mark.parametrize(
    "version,custom,border",
    [(0, False, False), (1, True, False), (2, True, True), (255, True, True)],
)
def test_native_font_response_preserves_app_report_without_enabling_upload(version, custom, border):
    result = decode_text_capability(build_packet(0xDD, [version]))
    assert result == {
        "source": "device_notification",
        "font_protocol_version": version,
        "custom_font_reported": custom,
        "font_border_reported": border,
        "native_text_upload_verified": False,
    }


@pytest.mark.parametrize(
    "data",
    [
        None,
        "aadd010189",
        b"",
        bytes.fromhex("aadd0087"),
        bytes.fromhex("aadd010188"),
        build_packet(0xDD, [1, 2]),
        build_packet(0xD4, [1]),
    ],
)
def test_native_font_capability_ignores_malformed_ack_and_unrelated_packets(data):
    assert decode_text_capability(data) is None
