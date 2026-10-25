import struct
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PIXEL = b"\x10\x20\x30\xff"


def cursor_bytes() -> bytes:
    """Build an opaque one-pixel CUR without using the production codec"""
    image = struct.pack("<IiiHHIIiiII", 40, 1, 2, 1, 32, 0, 8, 0, 0, 0, 0) + PIXEL + bytes(4)
    return struct.pack("<HHH", 0, 2, 1) + struct.pack("<BBBBHHII", 1, 1, 0, 0, 0, 0, len(image), 22) + image


def expected_xcursor() -> bytes:
    """Encode the expected solid-color output directly from the Xcursor layout"""
    sizes = (22, 24, 28, 32, 36, 40, 48, 56, 64, 72, 80, 88, 96)
    position = 16 + 12 * len(sizes)
    entries = bytearray()
    images = bytearray()
    for size in sizes:
        entries.extend(struct.pack("<III", 0xFFFD0002, size, position))
        image = struct.pack("<9I", 36, 0xFFFD0002, size, 1, size, size, 0, 0, 0) + PIXEL * size * size
        images.extend(image)
        position += len(image)
    return struct.pack("<4sIII", b"Xcur", 16, 0x10000, len(sizes)) + entries + images


def run_cli(*args: str | Path, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "cursorgen", *(str(arg) for arg in args)],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        timeout=30,
        check=False,
    )


class CLIAliasTests(unittest.TestCase):
    def test_hardlinked_destination_preserves_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.cur"
            original = cursor_bytes()
            source.write_bytes(original)
            output = root / "output"
            output.mkdir()
            destination = output / "source"
            destination.hardlink_to(source)

            result = run_cli(source, "-o", output)

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(destination.read_bytes(), original)

    def test_cross_job_hardlink_preserves_every_source(self) -> None:
        for reverse in (False, True):
            with self.subTest(reverse=reverse), TemporaryDirectory() as directory:
                root = Path(directory)
                first = root / "first.cur"
                second = root / "second.cur"
                original = cursor_bytes()
                first.write_bytes(original)
                second.write_bytes(original)
                output = root / "output"
                output.mkdir()
                destination = output / "first"
                destination.hardlink_to(second)
                sources = (second, first) if reverse else (first, second)

                result = run_cli(*sources, "-o", output)

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(first.read_bytes(), original)
                self.assertEqual(second.read_bytes(), original)
                self.assertEqual(destination.read_bytes(), original)
                self.assertFalse((output / "second").exists())

    def test_direct_destination_alias_preserves_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            original = cursor_bytes()
            source.write_bytes(original)

            result = run_cli(source, "-o", root)

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(source.read_bytes(), original)

    def test_symlinked_destination_preserves_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.cur"
            original = cursor_bytes()
            source.write_bytes(original)
            output = root / "output"
            output.mkdir()
            destination = output / "source"
            destination.symlink_to(source)

            result = run_cli(source, "-o", output)

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue(destination.is_symlink())
            self.assertEqual(destination.read_bytes(), original)

    def test_hardlinked_outputs_are_rejected_without_writes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.cur"
            second = root / "second.cur"
            original = cursor_bytes()
            first.write_bytes(original)
            second.write_bytes(original)
            output = root / "output"
            output.mkdir()
            sentinel = b"existing output"
            (output / "first").write_bytes(sentinel)
            (output / "second").hardlink_to(output / "first")

            result = run_cli(first, second, "-o", output)

            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(second.read_bytes(), original)
            self.assertEqual((output / "first").read_bytes(), sentinel)
            self.assertEqual((output / "second").read_bytes(), sentinel)

    def test_independent_inputs_convert_and_replace_existing_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.cur"
            second = root / "second.cur"
            original = cursor_bytes()
            first.write_bytes(original)
            second.write_bytes(original)
            output = root / "output"
            output.mkdir()
            (output / "first").write_bytes(b"old output")

            result = run_cli(first, second, "-o", output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(second.read_bytes(), original)
            self.assertEqual((output / "first").read_bytes(), expected_xcursor())
            self.assertEqual((output / "second").read_bytes(), expected_xcursor())

    def test_stdin_creates_missing_output_directory(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "output"

            result = run_cli("-", "-o", output, stdin=cursor_bytes())

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / "<stdin>").read_bytes(), expected_xcursor())

    def test_missing_input_reports_failure_and_converts_independent_input(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.cur"
            original = cursor_bytes()
            source.write_bytes(original)
            output = root / "output"

            result = run_cli(root / "missing.cur", source, "-o", output)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual((output / "source").read_bytes(), expected_xcursor())
            self.assertFalse((output / "missing").exists())

    def test_write_failure_preserves_source(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.cur"
            original = cursor_bytes()
            source.write_bytes(original)
            output = root / "output"
            destination = output / "source"
            destination.mkdir(parents=True)

            result = run_cli(source, "-o", output)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue(destination.is_dir())
