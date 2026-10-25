"""Parse length-delimited ANI chunks while rejecting incomplete records.

ANI delays use 1/60-second jiffies, converted to seconds in CursorFrame.
Absent sequence and rate chunks use natural frame order and the header rate.
"""

import struct
from itertools import repeat
from typing import Dict, Iterable, Iterator, List, Sequence, Set, Tuple, cast

from typing_extensions import Final

from cursorgen.formats import ANI_HEADER, ANIHeader
from cursorgen.parser.cur import CURParser
from cursorgen.utils.cursor import CursorFrame

RIFF_HEADER: Final = struct.Struct("<4sI4s")
RIFF_CHUNK_HEADER: Final = struct.Struct("<4sI")
UINT32_LE: Final = struct.Struct("<I")
RIFF_TAG_SIZE: Final = 4
RIFF_ALIGNMENT: Final = 2
RIFF_SIGNATURE: Final = b"RIFF"
ANI_TYPE: Final = b"ACON"
HEADER_CHUNK: Final = b"anih"
LIST_CHUNK: Final = b"LIST"
SEQ_CHUNK: Final = b"seq "
RATE_CHUNK: Final = b"rate"
FRAME_TYPE: Final = b"fram"
ICON_CHUNK: Final = b"icon"
ICON_FLAG: Final = 0x1
JIFFIES_PER_SECOND: Final = 60
SINGLETON_ERRORS: Final = {
    HEADER_CHUNK: "Duplicate or invalid animation header",
    SEQ_CHUNK: "Duplicate animation sequence",
    RATE_CHUNK: "Duplicate animation rates",
}


def _chunks(data: memoryview) -> Iterator[Tuple[bytes, memoryview]]:
    """Yield RIFF payload views, rejecting incomplete chunks and missing padding."""
    offset = 0
    while offset < len(data):
        if len(data) - offset < RIFF_CHUNK_HEADER.size:
            raise ValueError("Invalid animation structure: truncated chunk header")
        name, size = cast(Tuple[bytes, int], RIFF_CHUNK_HEADER.unpack_from(data, offset))
        start = offset + RIFF_CHUNK_HEADER.size
        end = start + size
        offset = end + size % RIFF_ALIGNMENT
        if offset > len(data):
            raise ValueError("Invalid animation structure: truncated chunk payload or padding")
        yield name, data[start:end]


def _unsigned(data: memoryview) -> List[int]:
    """Decode fixed-width integers and reject incomplete trailing values."""
    try:
        return [value for (value,) in UINT32_LE.iter_unpack(data)]
    except struct.error as error:
        raise ValueError(f"Invalid animation structure: {error}") from error


class ANIParser:
    @staticmethod
    def can_parse(blob: bytes) -> bool:
        return blob.startswith(RIFF_SIGNATURE) and blob[RIFF_CHUNK_HEADER.size : RIFF_HEADER.size] == ANI_TYPE

    def __init__(self, blob: bytes) -> None:
        if not self.can_parse(blob):
            raise ValueError("Not a .ani file")
        _, size, _ = RIFF_HEADER.unpack_from(blob)
        end = RIFF_CHUNK_HEADER.size + size
        if size < RIFF_TAG_SIZE or end > len(blob):
            raise ValueError("Invalid animation structure: invalid RIFF size")

        singletons: Dict[bytes, memoryview] = {}
        duplicates: Set[bytes] = set()
        frame_lists: List[memoryview] = []
        for name, data in _chunks(memoryview(blob)[RIFF_HEADER.size : end]):
            if name in SINGLETON_ERRORS:
                if name in singletons:
                    duplicates.add(name)
                singletons[name] = data
            elif name == LIST_CHUNK and bytes(data[:RIFF_TAG_SIZE]) == FRAME_TYPE:
                frame_lists.append(data[RIFF_TAG_SIZE:])
        for name, error in SINGLETON_ERRORS.items():
            if name in duplicates:
                raise ValueError(error)

        header_data = singletons.get(HEADER_CHUNK)
        if header_data is None:
            raise ValueError("Required animation header not found")
        if len(header_data) != ANI_HEADER.size:
            raise ValueError("Invalid animation header size")
        header = ANIHeader._make(ANI_HEADER.unpack(header_data))
        if header.size != ANI_HEADER.size:
            raise ValueError("Invalid animation header size")
        if not header.flags & ICON_FLAG:
            raise NotImplementedError("Raw BMP animation frames are not supported")

        frames: List[CursorFrame] = []
        for data in frame_lists:
            for name, payload in _chunks(data):
                if name == ICON_CHUNK:
                    # CUR image decoders require bytes for signature checks
                    frames.append(CURParser(payload.tobytes()).frames[0])
        frame_count, step_count = header.frame_count, header.step_count
        if not frames or len(frames) != frame_count or step_count == 0:
            raise ValueError("Animation frame count does not match its header")
        # Some published cursors set AF_SEQUENCE but omit the sequence chunk
        # Equal frame and step counts still describe a natural frame order
        order: Sequence[int] = range(frame_count)
        sequence_data = singletons.get(SEQ_CHUNK)
        if sequence_data is not None:
            order = _unsigned(sequence_data)
        if len(order) != step_count or any(index >= frame_count for index in order):
            raise ValueError("Invalid animation sequence")
        rate_data = singletons.get(RATE_CHUNK)
        delays: Iterable[int]
        if rate_data is not None:
            delays = _unsigned(rate_data)
            if len(delays) != step_count:
                raise ValueError("Animation rate count does not match its header")
        else:
            delays = repeat(header.display_rate, step_count)

        self.frames = [
            CursorFrame(frames[index].images, delay / JIFFIES_PER_SECOND) for index, delay in zip(order, delays)
        ]
