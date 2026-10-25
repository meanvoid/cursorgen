"""PNG compatibility handling around OpenCV's native image decoder.

APNG metadata is removed to select IDAT consistently for every frame count.
Grayscale transparency and 16-bit conversion retain cursor pixel semantics.
"""

import struct
from typing import Iterator, List, Optional, Tuple, Union, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from typing_extensions import Final

from cursorgen.utils.cursor import ALPHA_CHANNEL, CHANNEL_MAX, COLOR_CHANNELS

PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
PNG_CHUNK_HEADER: Final = struct.Struct(">I4s")
PNG_CRC_SIZE: Final = 4
PNG_CHUNK_OVERHEAD: Final = PNG_CHUNK_HEADER.size + PNG_CRC_SIZE
PNG_IHDR: Final = struct.Struct(">IIBBBBB")
PNG_GRAYSCALE: Final = 0
PNG_TRUECOLOR: Final = 2
PNG_ANIMATION_CONTROL: Final = b"acTL"
PNG_ANIMATION_CHUNKS: Final = (PNG_ANIMATION_CONTROL, b"fcTL", b"fdAT")
PNG_IMAGE_DATA: Final = b"IDAT"
PNG_IMAGE_END: Final = b"IEND"
PNG_TRANSPARENCY: Final = b"tRNS"
PNG_TRANSPARENT_GRAY: Final = struct.Struct(">H")
PNG_TRANSPARENT_RGB: Final = struct.Struct(">HHH")
BITS_PER_CHANNEL: Final = 8


def _png_chunks(blob: bytes) -> Iterator[Tuple[bytes, int, int]]:
    """Yield chunk types and byte ranges without copying payloads."""
    offset = len(PNG_SIGNATURE)
    while offset + PNG_CHUNK_OVERHEAD <= len(blob):
        length, kind = cast(Tuple[int, bytes], PNG_CHUNK_HEADER.unpack_from(blob, offset))
        end = offset + length + PNG_CHUNK_OVERHEAD
        if end > len(blob):
            raise ValueError("Truncated cursor PNG chunk")
        yield kind, offset, end
        if kind == PNG_IMAGE_END:
            return
        offset = end


def _png_default_image(blob: bytes) -> Union[bytes, bytearray]:
    """Strip APNG chunks so OpenCV decodes the default IDAT image."""
    filtered: Optional[bytearray] = None
    view = memoryview(blob)
    for kind, offset, end in _png_chunks(blob):
        if kind == PNG_ANIMATION_CONTROL and filtered is None:
            filtered = bytearray(view[:offset])
        elif filtered is not None and kind not in PNG_ANIMATION_CHUNKS:
            filtered.extend(view[offset:end])
        elif filtered is None and kind == PNG_IMAGE_DATA:
            return blob
    return blob if filtered is None else filtered


def _png_transparency(image: Union[NDArray[np.uint8], NDArray[np.uint16]], blob: bytes) -> Optional[NDArray[np.uint8]]:
    """Match PNG color keys before lossy sample conversion"""
    _, _, bit_depth, color_type, _, _, _ = PNG_IHDR.unpack_from(blob, len(PNG_SIGNATURE) + PNG_CHUNK_HEADER.size)
    if color_type not in (PNG_GRAYSCALE, PNG_TRUECOLOR):
        return None
    # OpenCV ignores grayscale tRNS, but retains the original sample precision
    for kind, offset, _ in _png_chunks(blob):
        if kind == PNG_IMAGE_DATA:
            return None
        if kind != PNG_TRANSPARENCY:
            continue
        data_offset = offset + PNG_CHUNK_HEADER.size
        key: Tuple[int, ...]
        if color_type == PNG_GRAYSCALE:
            (transparent,) = PNG_TRANSPARENT_GRAY.unpack_from(blob, data_offset)
            # OpenCV expands packed grayscale samples to the full uint8 range
            if bit_depth < BITS_PER_CHANNEL:
                transparent = transparent * CHANNEL_MAX // ((1 << bit_depth) - 1)
            key = (transparent,)
        else:
            key = PNG_TRANSPARENT_RGB.unpack_from(blob, data_offset)[::-1]
        lower = upper = key
        if image.ndim == 3 and image.shape[2] == ALPHA_CHANNEL + 1:
            # Match color samples independently of the decoder's alpha
            lower = (*key, 0)
            upper = (*key, np.iinfo(image.dtype).max)
        alpha = cv2.inRange(image, np.array(lower), np.array(upper))
        cv2.bitwise_not(alpha, dst=alpha)
        return cast("NDArray[np.uint8]", alpha)
    return None


def decode_png(blob: bytes) -> NDArray[np.uint8]:
    """Decode the PNG default image into writable, straight-alpha uint8 BGRA."""
    encoded = _png_default_image(blob)
    decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise ValueError("Invalid cursor PNG image")
    decoded = cast("Union[NDArray[np.uint8], NDArray[np.uint16]]", decoded)
    alpha = _png_transparency(decoded, blob)
    # Grayscale conversion saturates, while color conversion keeps the high byte
    if decoded.dtype == np.uint16:
        decoded = cv2.convertScaleAbs(decoded) if decoded.ndim == 2 else (decoded >> BITS_PER_CHANNEL).astype(np.uint8)
    if decoded.ndim == 2:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_GRAY2BGRA)
    elif decoded.shape[2] == COLOR_CHANNELS:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGR2BGRA)
    image = cast("NDArray[np.uint8]", decoded)
    if alpha is not None:
        image[:, :, ALPHA_CHANNEL] = alpha
    return image


def resize_nearest(image: NDArray[np.uint8], size: Tuple[int, int]) -> NDArray[np.uint8]:
    """Return independent BGRA pixels using pixel-center nearest sampling."""
    if image.shape[:2] == size[::-1]:
        return image.copy()
    if len(image.shape[:2]) != len(size):
        raise ValueError("Image dimensions and target size must have equal lengths")
    # OpenCV 4's fixed-point sampler drifts, so use the same floating-point
    # accumulation on both OpenCV 4 and 5 to keep cached Nix packages usable
    indices: List[NDArray[np.intp]] = []
    for source, target in zip(image.shape[:2], size[::-1]):
        coordinates = np.full(target, source / target, dtype=np.float64)
        coordinates[0] *= 0.5
        np.cumsum(coordinates, out=coordinates)
        indices.append(np.minimum(coordinates.astype(np.intp), source - 1))
    return image[indices[0][:, None], indices[1]]
