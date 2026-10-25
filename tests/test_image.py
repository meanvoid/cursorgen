import struct
import unittest
import zlib

import numpy as np

from cursorgen.parser.cur import CURParser
from cursorgen.utils.image import decode_png

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def animated_png(
    *,
    frames: int,
    separate_default: bool,
    color_type: int = 6,
    default_pixel: bytes = b"\0\0\xff\x53",
    animation_pixel: bytes = b"\xff\0\0\xff",
    metadata: bytes = b"",
) -> bytes:
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, color_type, 0, 0, 0))
    default_data = zlib.compress(b"\0" + default_pixel)
    split = len(default_data) // 2
    default_chunks = chunk(b"IDAT", default_data[:split]) + chunk(b"IDAT", default_data[split:])
    animation_data = zlib.compress(b"\0" + animation_pixel)
    result = SIGNATURE + header + metadata + chunk(b"acTL", struct.pack(">II", frames, 0))
    if separate_default:
        result += default_chunks
    sequence = 0
    for index in range(frames):
        result += chunk(b"fcTL", struct.pack(">IIIIIHHBB", sequence, 1, 1, 0, 0, 1, 10, 0, 0))
        sequence += 1
        if not separate_default and index == 0:
            result += default_chunks
        else:
            result += chunk(b"fdAT", struct.pack(">I", sequence) + animation_data)
            sequence += 1
    return result + chunk(b"tEXt", b"Comment\0Keep the default image") + chunk(b"IEND", b"")


class PNGDefaultImageTests(unittest.TestCase):
    def test_default_pixels_do_not_depend_on_animation_frame_count(self) -> None:
        expected = np.array([[[255, 0, 0, 83]]], dtype=np.uint8)
        for frames in (1, 2, 4):
            for separate in (False, True):
                with self.subTest(frames=frames, separate_default=separate):
                    image = decode_png(animated_png(frames=frames, separate_default=separate))
                    np.testing.assert_array_equal(image, expected)

    def test_palette_transparency_is_retained_with_a_separate_default(self) -> None:
        blob = animated_png(
            frames=2,
            separate_default=True,
            color_type=3,
            default_pixel=b"\0",
            animation_pixel=b"\1",
            metadata=chunk(b"PLTE", b"\x17\x5b\xb1\xff\0\0") + chunk(b"tRNS", b"\x53\xff"),
        )
        np.testing.assert_array_equal(decode_png(blob), np.array([[[177, 91, 23, 83]]], dtype=np.uint8))

    def test_grayscale_transparency_is_retained_with_a_separate_default(self) -> None:
        blob = animated_png(
            frames=2,
            separate_default=True,
            color_type=0,
            default_pixel=b"\x7f",
            animation_pixel=b"\xc8",
            metadata=chunk(b"tRNS", struct.pack(">H", 127)),
        )
        np.testing.assert_array_equal(decode_png(blob), np.array([[[127, 127, 127, 0]]], dtype=np.uint8))

    def test_cur_entry_uses_the_png_default_instead_of_an_animation_frame(self) -> None:
        png = animated_png(frames=3, separate_default=True)
        directory = struct.pack("<HHH", 0, 2, 1)
        entry = struct.pack("<BBBBHHII", 1, 1, 0, 0, 0, 0, len(png), 22)
        image = CURParser(directory + entry + png).frames[0][0].image
        np.testing.assert_array_equal(image, np.array([[[255, 0, 0, 83]]], dtype=np.uint8))

    def test_truncated_animation_chunk_is_rejected(self) -> None:
        png = animated_png(frames=2, separate_default=True)
        offset = png.index(b"acTL") - 4
        malformed = png[:offset] + struct.pack(">I", len(png)) + png[offset + 4 :]
        with self.assertRaises(ValueError):
            decode_png(malformed)
