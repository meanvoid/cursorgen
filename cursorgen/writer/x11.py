from typing import Iterable, List, Optional, Sequence

import numpy as np
from typing_extensions import Final

from cursorgen import xcursor
from cursorgen.utils.cursor import ALPHA_CHANNEL, BGRA_CHANNELS, CHANNEL_MAX, COLOR_CHANNELS, CursorFrame
from cursorgen.utils.image import resize_nearest

SIZES: Final[List[int]] = [22, 24, 28, 32, 36, 40, 48, 56, 64, 72, 80, 88, 96]


def _image_chunk(frame: CursorFrame, size: int, delay: int) -> xcursor.ImageChunk:
    # Prefer the larger source when two nominal sizes are equally close
    cursor = min(frame.images, key=lambda image: (abs(image.nominal - size), -image.nominal))
    if cursor.nominal <= 0:
        raise ValueError("Cursor nominal size must be positive")
    image = cursor.image
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != BGRA_CHANNELS:
        raise ValueError("Cursor images must be H x W x 4 uint8 BGRA arrays")
    source_height, source_width = image.shape[:2]
    hx, hy = cursor.hotspot
    if source_width == 0 or source_height == 0:
        raise ValueError("Cursor image dimensions must be positive")
    if not (0 <= hx <= source_width and 0 <= hy <= source_height):
        raise ValueError("Cursor hotspot must be within the image bounds")
    scale = size / cursor.nominal
    width = max(1, round(source_width * scale))
    height = max(1, round(source_height * scale))
    if width > xcursor.MAX_IMAGE_SIZE or height > xcursor.MAX_IMAGE_SIZE:
        raise ValueError("Scaled cursor dimensions exceed the Xcursor range")
    x = hx * width // source_width
    y = hy * height // source_height
    new_image = resize_nearest(image, (width, height))
    # Round premultiplied BGRA exactly, unlike OpenCV's RGBA2mRGBA conversion
    channels = np.multiply(new_image[:, :, :COLOR_CHANNELS], new_image[:, :, ALPHA_CHANNEL:], dtype=np.uint16)
    new_image[:, :, :COLOR_CHANNELS] = (channels + CHANNEL_MAX // 2) // CHANNEL_MAX
    return xcursor.ImageChunk(
        nominal=size,
        version=xcursor.IMAGE_VERSION,
        width=width,
        height=height,
        hotspot_x=x,
        hotspot_y=y,
        delay=delay,
        pixels=new_image.tobytes(),
    )


def to_xcursor(frames: Sequence[CursorFrame], sizes: Optional[Iterable[int]] = None) -> bytes:
    """Build Xcursor sizes from the closest source, preferring larger ties."""
    target_sizes = sorted(set(SIZES if sizes is None else sizes))
    if not target_sizes:
        raise ValueError(f"Cursor sizes must be between 1 and {xcursor.MAX_IMAGE_SIZE}")
    for size in target_sizes:
        if size <= 0 or size > xcursor.MAX_IMAGE_SIZE:
            raise ValueError(f"Cursor sizes must be between 1 and {xcursor.MAX_IMAGE_SIZE}")
    if not frames:
        raise ValueError("A cursor must contain images in every frame")
    images: List[xcursor.ImageChunk] = []
    for frame in frames:
        if not frame.images:
            raise ValueError("A cursor must contain images in every frame")
        delay = round(frame.delay * xcursor.MILLISECONDS_PER_SECOND)
        if not 0 <= delay <= xcursor.MAX_DELAY:
            raise ValueError("Cursor frame delay is outside the Xcursor range")
        for size in target_sizes:
            images.append(_image_chunk(frame, size, delay))
    return xcursor.encode(images)
