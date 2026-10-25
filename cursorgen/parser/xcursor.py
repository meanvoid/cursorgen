from collections import defaultdict
from typing import DefaultDict, List, Tuple

import numpy as np

from cursorgen import xcursor
from cursorgen.utils.cursor import ALPHA_CHANNEL, BGRA_CHANNELS, CHANNEL_MAX, COLOR_CHANNELS, CursorFrame, CursorImage


class XCursorParser:
    @staticmethod
    def can_parse(blob: bytes) -> bool:
        return blob.startswith(xcursor.MAGIC)

    def __init__(self, blob: bytes) -> None:
        images_by_size: DefaultDict[int, List[Tuple[CursorImage, float]]] = defaultdict(list)
        for chunk in xcursor.decode(blob):
            image = np.frombuffer(chunk.pixels, dtype=np.uint8).reshape(chunk.height, chunk.width, BGRA_CHANNELS).copy()
            alpha = image[:, :, ALPHA_CHANNEL:BGRA_CHANNELS].astype(np.uint16)
            # Round the inverse alpha transform so re-encoding preserves premultiplied colors
            channels = (image[:, :, :COLOR_CHANNELS].astype(np.uint16) * CHANNEL_MAX + alpha // 2) // np.where(
                alpha == 0, CHANNEL_MAX, alpha
            )
            np.minimum(channels, CHANNEL_MAX, out=image[:, :, :COLOR_CHANNELS])
            images_by_size[chunk.nominal].append(
                (
                    CursorImage(image, (chunk.hotspot_x, chunk.hotspot_y), chunk.nominal),
                    chunk.delay / xcursor.MILLISECONDS_PER_SECOND,
                )
            )

        frame_counts = {len(images) for images in images_by_size.values()}
        if len(frame_counts) != 1:
            raise ValueError("cursorgen does not support animations where each size has different number of frames")

        result: List[CursorFrame] = []
        for step in zip(*images_by_size.values()):
            frame_delay = step[0][1]
            if any(delay != frame_delay for _, delay in step):
                raise ValueError("cursorgen does not support animations where each size has a different frame delay")
            result.append(CursorFrame([image for image, _ in step], frame_delay))
        self.frames = result
