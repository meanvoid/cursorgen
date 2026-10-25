from typing import Iterator, List, Sequence, Tuple, Union, overload

import numpy as np
from numpy.typing import NDArray
from typing_extensions import Final

# Straight-alpha BGRA is the shared in-memory pixel layout
COLOR_CHANNELS: Final = 3
ALPHA_CHANNEL: Final = COLOR_CHANNELS
BGRA_CHANNELS: Final = COLOR_CHANNELS + 1
CHANNEL_MAX: Final = 255


class CursorImage:
    """An H x W x 4 uint8 NumPy image in BGRA order with straight alpha."""

    image: NDArray[np.uint8]
    hotspot: Tuple[int, int]
    nominal: int

    def __init__(self, image: NDArray[np.uint8], hotspot: Tuple[int, int], nominal: int) -> None:
        self.image = image
        self.hotspot = hotspot
        self.nominal = nominal

    def __repr__(self) -> str:
        return (
            f'CursorImage(image="Image with size {self.image.shape[1::-1]}", '
            f"hotspot={self.hotspot!r}, nominal={self.nominal!r})"
        )


class CursorFrame(Sequence[CursorImage]):
    """Cursor images with a frame delay in seconds, including fractional seconds"""

    images: List[CursorImage]
    # ANI stores 1/60-second jiffies and Xcursor stores milliseconds
    delay: float = 0

    def __init__(self, images: List[CursorImage], delay: float = 0) -> None:
        self.images = images
        self.delay = delay

    @overload
    def __getitem__(self, item: int) -> CursorImage: ...

    @overload
    def __getitem__(self, item: slice) -> List[CursorImage]: ...

    def __getitem__(self, item: Union[int, slice]) -> Union[CursorImage, List[CursorImage]]:
        return self.images[item]

    def __len__(self) -> int:
        return len(self.images)

    def __iter__(self) -> Iterator[CursorImage]:
        return iter(self.images)

    def __repr__(self) -> str:
        return f'CursorFrame(images=[{", ".join(repr(image) for image in self.images)}], delay={self.delay!r})'
