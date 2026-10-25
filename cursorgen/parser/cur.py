from typing import List

from typing_extensions import Final

from cursorgen.formats import ICON_DIRECTORY, ICON_ENTRY, IconDirectory, IconEntry
from cursorgen.parser.bmp import BMPParser
from cursorgen.utils.cursor import CursorFrame, CursorImage
from cursorgen.utils.image import PNG_SIGNATURE, decode_png


class CURParser:
    MAGIC: Final = b"\0\0\02\0"
    ICO_TYPE_CUR: Final = 2

    @staticmethod
    def can_parse(blob: bytes) -> bool:
        return blob.startswith(CURParser.MAGIC)

    def __init__(self, blob: bytes) -> None:
        if len(blob) < ICON_DIRECTORY.size:
            raise ValueError("Truncated cursor directory header")
        header = IconDirectory._make(ICON_DIRECTORY.unpack_from(blob))
        if header.reserved != 0 or header.type != self.ICO_TYPE_CUR:
            raise ValueError("Not a .cur file")
        directory_end = ICON_DIRECTORY.size + header.image_count * ICON_ENTRY.size
        if header.image_count == 0 or directory_end > len(blob):
            raise ValueError("Empty or truncated cursor directory")

        images: List[CursorImage] = []
        directory = memoryview(blob)[ICON_DIRECTORY.size : directory_end]
        for fields in ICON_ENTRY.iter_unpack(directory):
            entry = IconEntry._make(fields)
            if entry.size == 0 or entry.offset < directory_end or entry.offset + entry.size > len(blob):
                raise ValueError("Invalid cursor image offset or size")
            image_data = blob[entry.offset : entry.offset + entry.size]
            hotspot = (entry.hotspot_x, entry.hotspot_y)
            if image_data.startswith(PNG_SIGNATURE):
                # CUR entries use the PNG default image, not its animation
                image = decode_png(image_data)
            else:
                image = BMPParser(image_data).frame
            height, width = image.shape[:2]
            if not (0 <= hotspot[0] <= width and 0 <= hotspot[1] <= height):
                raise ValueError(f"Cursor hotspot {hotspot} is outside image {(width, height)}")
            images.append(CursorImage(image, hotspot, max(width, height)))

        self.frames = [CursorFrame(images)]
