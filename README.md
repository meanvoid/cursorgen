# cursorgen

`cursorgen` converts Windows cursors (`.cur` and animated `.ani`) and existing
Xcursor files into Xcursor files for Linux cursor themes on X11 and Wayland

`cursorgen` is a fork of [win2xcur](https://github.com/quantum5/win2xcur) that
preserves cursor colors and transparency using OpenCV and NumPy instead of
ImageMagick. It generates 13 sizes from 22 to 96 pixels with nearest-neighbor
scaling and preserves animation timing

## Installation

Python 3.7 or newer is required. Install the package from PyPI:

```sh
python -m pip install cursorgen
```

## Usage

Convert one file or a cursor pack:

```sh
cursorgen arrow.cur -o output
cursorgen windows-cursors/*.cur windows-cursors/*.ani -o output
```

The output directory is created automatically. `arrow.cur` becomes
`output/arrow`. Existing files are replaced, but input files are protected.
Use separate output directories for files with the same stem, such as
`arrow.cur` and `arrow.ani`

Try the bundled samples from the checkout:

```sh
cursorgen sample/crosshair.cur -o output/static
cursorgen sample/crosshair.ani -o output/animated
```

Run `python fetch_samples.py` to checksum-verify the samples and download fresh
copies if needed. The static crosshair comes from win2xcur.
The animated sample is a text-selection cursor from
[Yorumu's Matikanefukukitaru release](https://www.pixiv.net/artworks/93099359)

For use in a theme, put converted files in `<theme>/cursors/` under role names
such as `left_ptr` for the pointer and `xterm` for text selection, then select
the theme in your desktop settings. See the
[Xcursor theme documentation](https://www.x.org/archive/X11R7.5/doc/man/man3/Xcursor.3.html#toc6)
for directory layout and inheritance

## Nix

The flake supplies Python and all dependencies, pinned through `flake.lock`.
It supports `x86_64-linux`, `aarch64-linux`, and `aarch64-darwin`. Enable
[Nix flakes](https://nix.dev/concepts/flakes.html) and `nix-command`, then run
from the checkout:

```sh
nix run . -- sample/crosshair.cur -o output/nix
nix build .
./result/bin/cursorgen --help
```

## Development

Clone the repository and use Python 3.10 or newer for development tools and the
existing test suite:

```sh
git clone https://github.com/meanvoid/cursorgen.git
cd cursorgen
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
cursorgen sample/crosshair.cur -o output/dev
python -m unittest discover -s tests -v
pre-commit run --all-files
python -m build
```

CI also checks pip installation and sample conversion on every supported Python
version, including Python 3.7

For a Nix development shell, run `nix develop`, then use
`python -m cursorgen` to run with Nix's Python and libraries. Run
`nix flake check` to build the Nix package, run the existing unittest suite, and
check its Python imports. Build a wheel using the shell's build dependencies
with `python -m build --wheel --no-isolation`

Licensed under [GPL-3.0-or-later](LICENSE)
