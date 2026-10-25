import struct
from typing import Tuple, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from typing_extensions import Final

from cursorgen.formats import DIB_HEADER, DIBHeader
from cursorgen.utils.cursor import ALPHA_CHANNEL, BGRA_CHANNELS, CHANNEL_MAX, COLOR_CHANNELS

DIB_SIZE_FIELD: Final = struct.Struct("<I")
DIB_V4_HEADER_SIZE: Final = 108
DIB_V5_HEADER_SIZE: Final = 124
DIB_HEADER_SIZES: Final = frozenset({DIB_HEADER.size, DIB_V4_HEADER_SIZE, DIB_V5_HEADER_SIZE})
DIB_COLOR_PLANES: Final = 1
DIB_UNCOMPRESSED: Final = 0
DIB_BITFIELDS: Final = 3
DIB_RGB_MASKS: Final = struct.Struct("<III")
DIB_RGBA_MASKS: Final = struct.Struct("<IIII")
DIB_STANDARD_RGB_MASKS: Final = (0x00FF0000, 0x0000FF00, 0x000000FF)
DIB_STANDARD_ALPHA_MASK: Final = 0xFF000000
CURSOR_BITMAP_PLANES: Final = 2  # XOR image followed by its AND transparency mask
BITS_PER_BYTE: Final = 8
DIB_ROW_ALIGNMENT: Final = 4
DIB_ROW_BITS: Final = DIB_ROW_ALIGNMENT * BITS_PER_BYTE
PALETTE_ENTRY_SIZE: Final = 4
MASK_BIT_DEPTH: Final = 1
INDEXED_BIT_DEPTHS: Final = (MASK_BIT_DEPTH, 2, 4, BITS_PER_BYTE)
BGR555_BIT_DEPTH: Final = 16
BGR_BIT_DEPTH: Final = COLOR_CHANNELS * BITS_PER_BYTE
BGRA_BIT_DEPTH: Final = BGRA_CHANNELS * BITS_PER_BYTE
SUPPORTED_BIT_DEPTHS: Final = (*INDEXED_BIT_DEPTHS, BGR555_BIT_DEPTH, BGR_BIT_DEPTH, BGRA_BIT_DEPTH)
BGR555_BYTES_PER_PIXEL: Final = BGR555_BIT_DEPTH // BITS_PER_BYTE
BGR555_CHANNEL_BITS: Final = 5
BGR555_EXPANDED_MAX: Final = ((1 << BGR555_CHANNEL_BITS) - 1) << (BITS_PER_BYTE - BGR555_CHANNEL_BITS)


def _palette_indices(rows: NDArray[np.uint8], width: int, bpp: int) -> NDArray[np.uint8]:
    if bpp == MASK_BIT_DEPTH:
        return np.unpackbits(rows, axis=1, count=width)
    if bpp == BITS_PER_BYTE:
        return rows[:, :width]
    packed_width = (width * bpp + BITS_PER_BYTE - 1) // BITS_PER_BYTE
    shifts = np.arange(BITS_PER_BYTE - bpp, -1, -bpp, dtype=np.uint8)
    indices = (rows[:, :packed_width, None] >> shifts) & ((1 << bpp) - 1)
    return cast("NDArray[np.uint8]", indices.reshape(rows.shape[0], -1)[:, :width])


def _direct_color(rows: NDArray[np.uint8], width: int, bpp: int) -> NDArray[np.uint8]:
    height = rows.shape[0]
    if bpp == BGR555_BIT_DEPTH:
        pixels = rows[:, : width * BGR555_BYTES_PER_PIXEL].reshape(height, width, BGR555_BYTES_PER_PIXEL)
        image = cv2.cvtColor(pixels, cv2.COLOR_BGR5552BGRA)
        # Expand all five color bits to the full 0–255 range
        image[:, :, :COLOR_CHANNELS] = (
            image[:, :, :COLOR_CHANNELS].astype(np.uint16) * CHANNEL_MAX // BGR555_EXPANDED_MAX
        )
        return cast("NDArray[np.uint8]", image)
    if bpp == BGR_BIT_DEPTH:
        pixels = rows[:, : width * COLOR_CHANNELS].reshape(height, width, COLOR_CHANNELS)
        return cast("NDArray[np.uint8]", cv2.cvtColor(pixels, cv2.COLOR_BGR2BGRA))
    return rows[:, : width * BGRA_CHANNELS].reshape(height, width, BGRA_CHANNELS).copy()


def _bitfield_masks(blob: bytes, size: int, bpp: int) -> Tuple[Tuple[int, ...], int]:
    if bpp not in (BGR555_BIT_DEPTH, BGRA_BIT_DEPTH):
        raise ValueError("Bitfield cursor bitmaps require 16-bit or 32-bit pixels")
    mask_struct = DIB_RGB_MASKS if size == DIB_HEADER.size else DIB_RGBA_MASKS
    if len(blob) < DIB_HEADER.size + mask_struct.size:
        raise ValueError("Truncated cursor bitfield masks")
    masks = mask_struct.unpack_from(blob, DIB_HEADER.size)
    used_bits = 0
    for channel, mask in enumerate(masks):
        if not mask:
            if channel < COLOR_CHANNELS:
                raise ValueError("Cursor bitfield RGB masks must be nonzero")
            continue
        channel_max = mask >> ((mask & -mask).bit_length() - 1)
        if mask >= 1 << bpp or mask & used_bits or channel_max & (channel_max + 1):
            raise ValueError("Cursor bitfield masks must be contiguous, disjoint, and fit the pixel depth")
        used_bits |= mask
    alpha_mask = masks[ALPHA_CHANNEL] if len(masks) == BGRA_CHANNELS else 0
    if not alpha_mask and bpp == BGRA_BIT_DEPTH and masks[:COLOR_CHANNELS] == DIB_STANDARD_RGB_MASKS:
        # Standard 32-bit cursor pixels retain their legacy high-byte alpha
        alpha_mask = DIB_STANDARD_ALPHA_MASK
    palette_start = size + (mask_struct.size if size == DIB_HEADER.size else 0)
    return (masks[2], masks[1], masks[0], alpha_mask), palette_start


def _bitfield_color(rows: NDArray[np.uint8], width: int, bpp: int, masks: Tuple[int, ...]) -> NDArray[np.uint8]:
    pixels = rows.view("<u2" if bpp == BGR555_BIT_DEPTH else "<u4")[:, :width]
    image = np.empty((rows.shape[0], width, BGRA_CHANNELS), dtype=np.uint8)
    for channel, mask in enumerate(masks):
        if not mask:
            image[:, :, channel] = 0
            continue
        shift = (mask & -mask).bit_length() - 1
        channel_max = mask >> shift
        values = ((pixels & mask) >> shift).astype(np.uint64)
        image[:, :, channel] = values * CHANNEL_MAX // channel_max
    return image


class BMPParser:
    """Decode cursor DIBs, retaining Windows alpha/mask semantics."""

    @staticmethod
    def can_parse(blob: bytes) -> bool:
        """Check if the blob is one of the supported BMP types."""
        if len(blob) < DIB_HEADER.size:
            return False
        return DIB_SIZE_FIELD.unpack_from(blob)[0] in DIB_HEADER_SIZES

    def __init__(self, blob: bytes) -> None:
        if len(blob) < DIB_HEADER.size:
            raise ValueError("Truncated cursor bitmap header")
        header = DIBHeader._make(DIB_HEADER.unpack_from(blob))
        size, width, height, bpp = header.size, header.width, header.height, header.depth

        if size not in DIB_HEADER_SIZES or size > len(blob):
            raise ValueError(f"Unsupported or truncated DIB header: {size}")
        if width <= 0 or height == 0 or height % CURSOR_BITMAP_PLANES:
            raise ValueError(f"Invalid cursor bitmap dimensions: {width} x {height}")
        if header.planes != DIB_COLOR_PLANES or header.compression not in (DIB_UNCOMPRESSED, DIB_BITFIELDS):
            raise ValueError("Only uncompressed single-plane cursor bitmaps are supported")
        if bpp not in SUPPORTED_BIT_DEPTHS:
            raise ValueError(f"Unsupported cursor bitmap depth: {bpp}")
        masks: Tuple[int, ...] = ()
        palette_start = size
        has_alpha = bpp == BGRA_BIT_DEPTH
        if header.compression == DIB_BITFIELDS:
            masks, palette_start = _bitfield_masks(blob, size, bpp)
            has_alpha = bool(masks[ALPHA_CHANNEL])

        bottom_up = height > 0
        height = abs(height) // CURSOR_BITMAP_PLANES
        xor_size = self._row_size(bpp, width) * height
        and_size = self._row_size(MASK_BIT_DEPTH, width) * height
        indexed = bpp in INDEXED_BIT_DEPTHS
        palette_colors = header.colors_used or (1 << bpp if indexed else 0)
        if indexed and palette_colors > 1 << bpp:
            raise ValueError("Cursor palette exceeds the bitmap bit depth")
        palette_size = palette_colors * PALETTE_ENTRY_SIZE
        xor_start = palette_start + palette_size
        and_start = xor_start + xor_size
        if and_start > len(blob):
            raise ValueError("Truncated cursor palette or bitmap")
        if not has_alpha and and_start + and_size > len(blob):
            raise ValueError("Truncated cursor transparency mask")

        rows = np.frombuffer(blob, dtype=np.uint8, count=xor_size, offset=xor_start).reshape(height, -1)
        if bottom_up:
            rows = rows[::-1]
        if indexed:
            indices = _palette_indices(rows, width, bpp)
            if indices.max() >= palette_colors:
                raise ValueError("Cursor palette index exceeds its palette")
            palette = np.frombuffer(blob, dtype=np.uint8, count=palette_size, offset=palette_start).reshape(
                -1, PALETTE_ENTRY_SIZE
            )
            image = palette[indices]
        elif masks:
            image = _bitfield_color(rows, width, bpp, masks)
        else:
            image = _direct_color(rows, width, bpp)
        if has_alpha and image[:, :, ALPHA_CHANNEL].any():
            self.frame = image
            return
        if and_start + and_size > len(blob):
            raise ValueError("Cursor bitmap has neither alpha data nor a complete transparency mask")
        mask = np.frombuffer(blob, dtype=np.uint8, count=and_size, offset=and_start).reshape(height, -1)
        if bottom_up:
            mask = mask[::-1]
        image[:, :, ALPHA_CHANNEL] = (1 - np.unpackbits(mask, axis=1, count=width)) * CHANNEL_MAX
        self.frame = image

    @staticmethod
    def _row_size(bpp: int, width: int) -> int:
        """Return the bitmap stride, aligned to four bytes."""
        return ((bpp * width + DIB_ROW_BITS - 1) // DIB_ROW_BITS) * DIB_ROW_ALIGNMENT
