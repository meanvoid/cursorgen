"""Decode CUR, ANI, and Xcursor files into straight-alpha BGRA frames.

Parser results expose decoded frames without retaining the encoded input blob.
"""

from typing import List, Type, Union

from cursorgen.parser.ani import ANIParser
from cursorgen.parser.bmp import BMPParser
from cursorgen.parser.cur import CURParser
from cursorgen.parser.xcursor import XCursorParser

__all__ = [
    "ANIParser",
    "BMPParser",
    "CURParser",
    "XCursorParser",
    "PARSERS",
    "open_blob",
]

PARSERS: List[Union[Type[CURParser], Type[ANIParser], Type[XCursorParser]]] = [
    CURParser,
    ANIParser,
    XCursorParser,
]


def open_blob(blob: bytes) -> Union[CURParser, ANIParser, XCursorParser]:
    for parser in PARSERS:
        if parser.can_parse(blob):
            return parser(blob)
    raise ValueError("Unsupported file format")
