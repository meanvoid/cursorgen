"""Shared Xcursor binary layouts for X11 and Wayland cursor themes.

Pixel payloads use premultiplied BGRA and frame delays use milliseconds.
Parsing accepts extended headers, while writing emits canonical header sizes.
"""

import struct
from typing import List, NamedTuple, Sequence, Union

from typing_extensions import Final

from cursorgen.utils.cursor import BGRA_CHANNELS

MAGIC: Final = b"Xcur"
VERSION: Final = 0x1_0000
IMAGE_TYPE: Final = 0xFFFD0002
FILE_HEADER: Final = struct.Struct("<4sIII")
TOC_ENTRY: Final = struct.Struct("<III")
IMAGE_HEADER: Final = struct.Struct("<9I")
FILE_HEADER_SIZE: Final = FILE_HEADER.size
TOC_ENTRY_SIZE: Final = TOC_ENTRY.size
IMAGE_HEADER_SIZE: Final = IMAGE_HEADER.size
MAX_IMAGE_SIZE: Final = 0x7FFF
MAX_DELAY: Final = 0xFFFFFFFF
IMAGE_VERSION: Final = 1
MILLISECONDS_PER_SECOND: Final = 1000


class ImageChunk(NamedTuple):
    """An image record with premultiplied BGRA pixels and a millisecond delay."""

    nominal: int
    version: int
    width: int
    height: int
    hotspot_x: int
    hotspot_y: int
    delay: int
    pixels: Union[bytes, memoryview]


def decode(blob: bytes) -> List[ImageChunk]:
    """Read image chunks in table order, skipping unknown chunk types."""
    if len(blob) < FILE_HEADER_SIZE:
        raise ValueError("Invalid Xcursor structure: truncated file header")
    magic, header_size, version, count = FILE_HEADER.unpack_from(blob)
    if magic != MAGIC or version != VERSION:
        raise ValueError("Invalid Xcursor structure: unsupported file magic or version")
    if not FILE_HEADER_SIZE <= header_size <= len(blob):
        raise ValueError("Invalid Xcursor structure: invalid file header size")
    if count > (len(blob) - header_size) // TOC_ENTRY_SIZE:
        raise ValueError("Invalid Xcursor structure: truncated table of contents")

    table_end = header_size + count * TOC_ENTRY_SIZE
    data = memoryview(blob)
    images: List[ImageChunk] = []
    for chunk_type, nominal, position in TOC_ENTRY.iter_unpack(data[header_size:table_end]):
        if chunk_type != IMAGE_TYPE:
            continue
        if position < table_end or position > len(blob) - IMAGE_HEADER_SIZE:
            raise ValueError("Invalid Xcursor structure: invalid image position")
        (
            image_header_size,
            image_type,
            image_nominal,
            image_version,
            width,
            height,
            hotspot_x,
            hotspot_y,
            delay,
        ) = IMAGE_HEADER.unpack_from(blob, position)
        if not IMAGE_HEADER_SIZE <= image_header_size <= len(blob) - position:
            raise ValueError("Invalid Xcursor structure: invalid image header size")
        if image_type != IMAGE_TYPE or image_nominal != nominal:
            raise ValueError("Invalid Xcursor structure: image does not match its table entry")
        if not (0 < width <= MAX_IMAGE_SIZE and 0 < height <= MAX_IMAGE_SIZE):
            raise ValueError("Invalid Xcursor structure: invalid image dimensions")
        # libXcursor accepts hotspots on the right and bottom image boundaries
        if hotspot_x > width or hotspot_y > height:
            raise ValueError("Invalid Xcursor structure: invalid image hotspot")
        pixels_start = position + image_header_size
        pixels_end = pixels_start + width * height * BGRA_CHANNELS
        if pixels_end > len(blob):
            raise ValueError("Invalid Xcursor structure: truncated image pixels")
        # Image versions are informational, unlike the required file version
        images.append(
            ImageChunk(
                nominal, image_version, width, height, hotspot_x, hotspot_y, delay, data[pixels_start:pixels_end]
            )
        )
    return images


def encode(images: Sequence[ImageChunk]) -> bytes:
    """Pack canonical headers and image payloads after their table of contents."""
    position = FILE_HEADER_SIZE + len(images) * TOC_ENTRY_SIZE
    total_size = position
    for image in images:
        if not (0 < image.width <= MAX_IMAGE_SIZE and 0 < image.height <= MAX_IMAGE_SIZE):
            raise ValueError("Invalid Xcursor image dimensions")
        if not (0 <= image.hotspot_x <= image.width and 0 <= image.hotspot_y <= image.height):
            raise ValueError("Invalid Xcursor image hotspot")
        if len(image.pixels) != image.width * image.height * BGRA_CHANNELS:
            raise ValueError("Invalid Xcursor image pixel length")
        total_size += IMAGE_HEADER_SIZE + len(image.pixels)

    blob = bytearray(total_size)
    FILE_HEADER.pack_into(blob, 0, MAGIC, FILE_HEADER_SIZE, VERSION, len(images))
    offset = FILE_HEADER_SIZE
    for image in images:
        TOC_ENTRY.pack_into(blob, offset, IMAGE_TYPE, image.nominal, position)
        IMAGE_HEADER.pack_into(
            blob,
            position,
            IMAGE_HEADER_SIZE,
            IMAGE_TYPE,
            image.nominal,
            image.version,
            image.width,
            image.height,
            image.hotspot_x,
            image.hotspot_y,
            image.delay,
        )
        pixels_start = position + IMAGE_HEADER_SIZE
        position = pixels_start + len(image.pixels)
        blob[pixels_start:position] = image.pixels
        offset += TOC_ENTRY_SIZE
    return bytes(blob)
