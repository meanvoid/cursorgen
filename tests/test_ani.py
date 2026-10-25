import struct
import unittest

from cursorgen.parser.ani import ANIParser
from cursorgen.parser.cur import CURParser


def riff_chunk(name: bytes, data: bytes) -> bytes:
    return name + struct.pack("<I", len(data)) + data + b"\0" * (len(data) % 2)


def bitmap(pixel: bytes, *, cursor: bool) -> bytes:
    height = 2 if cursor else 1
    header = struct.pack("<IiiHHIIiiII", 40, 1, height, 1, 32, 0, 4, 0, 0, 0, 0)
    return header + pixel + (bytes(4) if cursor else b"")


def cursor(pixel: bytes) -> bytes:
    dib = bitmap(pixel, cursor=True)
    directory = struct.pack("<HHH", 0, 2, 1)
    entry = struct.pack("<BBBBHHII", 1, 1, 0, 0, 0, 0, len(dib), 22)
    return directory + entry + dib


def animation(
    icons: list[bytes],
    *,
    flags: int = 1,
    sequence: list[int] | None = None,
    rates: list[int] | None = None,
    display_rate: int = 6,
) -> bytes:
    steps = len(icons) if sequence is None else len(sequence)
    header = struct.pack("<9I", 36, len(icons), steps, 0, 0, 0, 0, display_rate, flags)
    chunks = riff_chunk(b"anih", header)
    if sequence is not None:
        chunks += riff_chunk(b"seq ", struct.pack(f"<{len(sequence)}I", *sequence))
    if rates is not None:
        chunks += riff_chunk(b"rate", struct.pack(f"<{len(rates)}I", *rates))
    chunks += riff_chunk(b"LIST", b"fram" + b"".join(riff_chunk(b"icon", icon) for icon in icons))
    body = b"ACON" + chunks
    return b"RIFF" + struct.pack("<I", len(body)) + body


class ANIParserTests(unittest.TestCase):
    def test_short_cur_headers_raise_value_error(self) -> None:
        header = struct.pack("<HHH", 0, 2, 1)
        for size in range(len(header)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                CURParser(header[:size])

    def test_nested_short_cur_headers_raise_value_error(self) -> None:
        header = struct.pack("<HHH", 0, 2, 1)
        for size in range(len(header)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                ANIParser(animation([header[:size]]))

    def test_nested_truncated_cur_directory_raises_value_error(self) -> None:
        cur = cursor(bytes((10, 20, 30, 255)))
        for size in (6, 7, 21):
            with self.subTest(size=size), self.assertRaises(ValueError):
                ANIParser(animation([cur[:size]]))

    def test_raw_bmp_frames_are_explicitly_unsupported(self) -> None:
        dib = bitmap(bytes((10, 20, 30, 255)), cursor=False)
        bmp = struct.pack("<2sIHHI", b"BM", 14 + len(dib), 0, 0, 54) + dib
        for payload in (dib, bmp):
            for flags in (0, 2):
                with self.subTest(file_header=payload.startswith(b"BM"), flags=flags):
                    with self.assertRaises(NotImplementedError):
                        ANIParser(animation([payload], flags=flags))

    def test_raw_bmp_requires_valid_animation_header(self) -> None:
        dib = bitmap(bytes((10, 20, 30, 255)), cursor=False)
        header = struct.pack("<9I", 35, 1, 1, 1, 1, 32, 1, 6, 0)
        body = b"ACON" + riff_chunk(b"anih", header) + riff_chunk(b"LIST", b"fram" + riff_chunk(b"icon", dib))
        with self.assertRaises(ValueError):
            ANIParser(b"RIFF" + struct.pack("<I", len(body)) + body)

    def test_sequence_preserves_reordered_repeated_frames_and_rates(self) -> None:
        first = bytes((10, 20, 30, 255))
        second = bytes((40, 50, 60, 255))
        frames = ANIParser(
            animation([cursor(first), cursor(second)], flags=3, sequence=[1, 0, 1], rates=[3, 12, 30])
        ).frames
        self.assertEqual(len(frames), 3)
        for frame, pixel, delay in zip(frames, (second, first, second), (0.05, 0.2, 0.5), strict=True):
            self.assertEqual(len(frame), 1)
            self.assertEqual(frame[0].image.shape, (1, 1, 4))
            self.assertEqual(frame[0].image.tobytes(), pixel)
            self.assertEqual(frame[0].hotspot, (0, 0))
            self.assertAlmostEqual(frame.delay, delay)

    def test_natural_order_and_default_rates_with_omitted_sequence(self) -> None:
        pixels = (bytes((10, 20, 30, 255)), bytes((40, 50, 60, 255)))
        for flags in (1, 3):
            with self.subTest(flags=flags):
                frames = ANIParser(animation([cursor(pixel) for pixel in pixels], flags=flags, display_rate=9)).frames
                self.assertEqual(len(frames), 2)
                for frame, pixel in zip(frames, pixels, strict=True):
                    self.assertEqual(frame[0].image.tobytes(), pixel)
                    self.assertAlmostEqual(frame.delay, 0.15)
