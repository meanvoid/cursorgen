"""Fixed binary layouts and typed Windows cursor records."""

import struct
from typing import NamedTuple

from typing_extensions import Final


class IconDirectory(NamedTuple):
    reserved: int
    type: int
    image_count: int


class IconEntry(NamedTuple):
    width: int
    height: int
    colors: int
    reserved: int
    hotspot_x: int
    hotspot_y: int
    size: int
    offset: int


class DIBHeader(NamedTuple):
    size: int
    width: int
    height: int
    planes: int
    depth: int
    compression: int
    image_size: int
    pixels_per_meter_x: int
    pixels_per_meter_y: int
    colors_used: int
    colors_important: int


class ANIHeader(NamedTuple):
    size: int
    frame_count: int
    step_count: int
    width: int
    height: int
    bit_count: int
    planes: int
    display_rate: int
    flags: int


# Fixed-size headers use the stdlib struct/namedtuple recipe without a codec layer
ICON_DIRECTORY: Final = struct.Struct("<HHH")
ICON_ENTRY: Final = struct.Struct("<BBBBHHII")
DIB_HEADER: Final = struct.Struct("<IiiHHIIiiII")
ANI_HEADER: Final = struct.Struct("<9I")
