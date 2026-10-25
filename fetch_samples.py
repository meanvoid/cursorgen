#!/usr/bin/env python3
"""Download the original sample cursors with pinned SHA-256 checksums.

Cached files are hashed as streams before reuse, without loading them in full.
"""

import argparse
import hashlib
import io
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, cast

from typing_extensions import Final

DOWNLOAD_TIMEOUT_SECONDS: Final = 60
USER_AGENT: Final = "cursorgen/0.1"
ARCHIVE_METADATA_ENCODING: Final = "cp932"
DEFAULT_OUTPUT: Final = Path("sample")

# Quantum created the static example by hand in this win2xcur commit
STATIC_URL = (
    "https://raw.githubusercontent.com/quantum5/win2xcur/0391d63e5e37b1658cfee029e75b9c63434b7819/sample/crosshair.cur"
)
STATIC_SHA256 = "0199a94aed00e5937b9f799ece7271c618c4ec7c0f58d03dd3c092519679259e"

# Yorumu's original distribution, linked at https://www.pixiv.net/artworks/93099359
ANIMATED_URL = (
    "https://www.dropbox.com/s/tnezo4s8e7yuznl/"
    "%E3%83%9E%E3%83%81%E3%82%AB%E3%83%8D%E3%83%95%E3%82%AF%E3%82%AD%E3%82%BF%E3%83%AB"
    "%E3%80%80%E3%83%9E%E3%82%A6%E3%82%B9%E3%82%AB%E3%83%BC%E3%82%BD%E3%83%AB.zip?dl=1"
)
ARCHIVE_SHA256 = "b55cf9a9e76e6923171718f75534166599d6e5ad7abcbe5f782affcad5d3708c"
ANIMATED_SHA256 = "e6e2aa4245d375fddf905401f880c9b5b7bdb41baa31e798019148ad5fd4d991"
ANIMATED_MEMBER = (
    "マチカネフクキタル　マウスカーソル/アニメーション/マチカネフクキタル　マウスカーソル　テキスト選択.ani"
)


@dataclass(frozen=True)
class Sample:
    filename: str
    sha256: str
    url: str
    download_sha256: str
    archive_member: Optional[str] = None


SAMPLES: Final = (
    Sample("crosshair.cur", STATIC_SHA256, STATIC_URL, STATIC_SHA256),
    Sample(
        "crosshair.ani",
        ANIMATED_SHA256,
        ANIMATED_URL,
        ARCHIVE_SHA256,
        ANIMATED_MEMBER,
    ),
)


class Options(argparse.Namespace):
    output: Path


def fetch(url: str, sha256: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        data = cast(bytes, response.read())
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"Download checksum mismatch: {url}")
    return data


def main() -> None:
    """Fetch, extract, and verify samples before replacing cached files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT, help="Directory for downloaded samples")
    destination = parser.parse_args(namespace=Options()).output
    destination.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        path = destination / sample.filename
        if path.is_file():
            with path.open("rb") as cached:
                checksum = hashlib.sha256()
                for block in iter(lambda: cached.read(65536), b""):
                    checksum.update(block)
                if checksum.hexdigest() == sample.sha256:
                    continue
        data = fetch(sample.url, sample.download_sha256)
        if sample.archive_member is not None:
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                # Python 3.7 decodes legacy ZIP names as CP437, not CP932
                members = {
                    (
                        member.filename
                        if member.flag_bits & 0x800
                        else member.filename.encode("cp437").decode(ARCHIVE_METADATA_ENCODING)
                    ): member
                    for member in bundle.infolist()
                }
                data = bundle.read(members[sample.archive_member])
        if hashlib.sha256(data).hexdigest() != sample.sha256:
            raise ValueError(f"Sample checksum mismatch: {sample.filename}")
        with tempfile.TemporaryDirectory(dir=destination) as directory:
            temporary = Path(directory) / sample.filename
            temporary.write_bytes(data)
            temporary.replace(path)
        print(f"Downloaded {sample.filename}")


if __name__ == "__main__":
    main()
