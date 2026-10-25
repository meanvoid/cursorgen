import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import BinaryIO, List, NamedTuple, Optional, Tuple, Union, cast

from rich.console import Console
from rich.progress import track
from typing_extensions import Final

from cursorgen.parser import open_blob
from cursorgen.writer import to_xcursor

STDIN_ARGUMENT: Final = "-"
LOGGER: Final = logging.getLogger(__name__)
STDIN_FILENAME: Final = "<stdin>"
DUPLICATE_OUTPUT_ERROR: Final = "input files must have distinct output names"
INPUT_OVERWRITE_ERROR: Final = "output files must not overwrite input files; choose another output directory"


class Options(argparse.Namespace):
    files: List[str]
    output: Path


class ConversionJob(NamedTuple):
    name: str
    source: Optional[Path]
    destination: Path


def _file_identity(path: Path) -> Union[Tuple[int, int], Path]:
    try:
        info = path.stat()
    except OSError:
        # Missing paths still need to be checked for name collisions
        return path.resolve()
    return info.st_dev, info.st_ino


def _process(job: ConversionJob) -> bool:
    try:
        if job.source is None:
            blob = cast(BinaryIO, sys.stdin.buffer).read()
        else:
            blob = job.source.read_bytes()
        cursor = open_blob(blob)
        job.destination.write_bytes(to_xcursor(cursor.frames))
    except Exception:
        LOGGER.exception("Error occurred while processing %s:", job.name)
        return False
    return True


def _validate_jobs(jobs: List[ConversionJob]) -> None:
    """Reject output aliases before any conversion can write."""
    destinations = [_file_identity(job.destination) for job in jobs]
    if len(set(destinations)) != len(jobs):
        raise ValueError(DUPLICATE_OUTPUT_ERROR)
    sources = {_file_identity(job.source) for job in jobs if job.source is not None}
    if not sources.isdisjoint(destinations):
        raise ValueError(INPUT_OVERWRITE_ERROR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Converts Windows and Xcursor files to Xcursor for X11 and Wayland.")
    parser.add_argument(
        "files",
        nargs="+",
        help="Cursor files to convert (*.cur, *.ani, Xcursor); use - for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to store converted cursor files (created if missing).",
    )

    args = parser.parse_args(namespace=Options())
    jobs: List[ConversionJob] = []
    for name in args.files:
        if name == STDIN_ARGUMENT:
            source = None
            destination = args.output / STDIN_FILENAME
        else:
            source = Path(name)
            destination = args.output / source.stem
        jobs.append(ConversionJob(name, source, destination))
    try:
        _validate_jobs(jobs)
    except ValueError as error:
        parser.error(str(error))
    try:
        args.output.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        parser.error(f"cannot create output directory: {error}")

    console = Console(stderr=True)
    with ThreadPoolExecutor() as pool:
        successes = sum(
            track(
                pool.map(_process, jobs),
                total=len(jobs),
                description="Converting cursors",
                console=console,
                disable=not console.is_terminal,
            )
        )
    return int(successes != len(jobs))


if __name__ == "__main__":
    sys.exit(main())
