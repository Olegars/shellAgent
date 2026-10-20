"""PNG из пикселей окна и уменьшение кадра для модели."""

from __future__ import annotations

import struct
import zlib


def bgra_to_rgba(data: bytes) -> bytes:
    buf = bytearray(data)
    for i in range(0, len(buf) - 3, 4):
        buf[i], buf[i + 2] = buf[i + 2], buf[i]
        buf[i + 3] = 255
    return bytes(buf)


def half(rgba: bytes, width: int, height: int) -> tuple[bytes, int, int]:
    nw, nh = width // 2, height // 2
    src = memoryview(rgba)
    out = bytearray(nw * nh * 4)
    offset = 0
    row_bytes = width * 4
    for y in range(nh):
        row = (y * 2) * row_bytes
        for x in range(nw):
            start = row + (x * 2) * 4
            out[offset : offset + 4] = src[start : start + 4]
            offset += 4
    return bytes(out), nw, nh


def fit_rgba(rgba: bytes, width: int, height: int, max_width: int = 1280) -> tuple[bytes, int, int, float]:
    scale = 1.0
    while width > max_width and width % 2 == 0 and height % 2 == 0:
        rgba, width, height = half(rgba, width, height)
        scale *= 0.5
    return rgba, width, height, scale


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    if width <= 0 or height <= 0 or len(rgba) != width * height * 4:
        raise ValueError("размер кадра не совпал с буфером")

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(rgba[y * stride : (y + 1) * stride])
    compressed = zlib.compress(bytes(raw), 6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
