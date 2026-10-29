"""Two-slot experiment based on btsnoop records 550..580, not a general GIF format.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

from collections.abc import Sequence

from .pixel_protocol import (
    build_packet,
    iter_pixel_update_packets,
    row_major_frame_to_updates,
)


def build_two_picture_sequence(
    frames: Sequence[Sequence[int]],
) -> list[tuple[str, bytes, float]]:
    """Keep captured command/slot order with conservative upload pacing.

    D0 profile 05/64/64 and action bytes are opaque captured settings. Do not
    extrapolate extra slots, a speed unit, sync, or an interpretation of DC(00).
    DA waits use the physically verified 300ms still-image upload cadence;
    playback speed is owned by the curtain, not these upload waits.
    """
    if len(frames) != 2:
        raise ValueError("exactly two pictures are supported by this experiment")
    checked = []
    for frame in frames:
        if len(frame) != 400 or any(
            type(p) is not int or not (0 <= p <= 180 or p in (254, 255)) for p in frame
        ):
            raise ValueError("each picture needs exactly 400 supported integer colors")
        checked.append(list(frame))

    sequence = [("captured D0 initialization", bytes.fromhex("aad0040564640752"), 0.025)]
    for slot, frame in enumerate(checked, 1):
        sequence.append((f"slot {slot} begin", build_packet(0xD7, [slot, 0]), 0.025))
        if slot == 1:
            sequence.append(
                ("captured D0 upload settings", bytes.fromhex("aad004056464004b"), 0.25)
            )
        updates = sorted(row_major_frame_to_updates(frame), key=lambda p: p[0] * 20 + p[1])
        packets = [
            build_packet(0xDA, [slot, *packet[4:-1]])
            for packet in iter_pixel_update_packets(updates)
        ]
        if [len(p) for p in packets] != [242] * 5 + [20]:
            raise RuntimeError("two-picture framing invariant failed")
        sequence.extend(
            (f"slot {slot} DA {number}/6", packet, 0.30) for number, packet in enumerate(packets, 1)
        )
        sequence.append((f"slot {slot} end", build_packet(0xD7, [slot, 2]), 0.025))
    sequence.extend(
        [
            ("captured D0 playback", bytes.fromhex("aad004056464024d"), 0.025),
            ("captured trailing DC command", bytes.fromhex("aadc010087"), 0.20),
        ]
    )
    return sequence
