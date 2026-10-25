{
  description = "A fork of win2xcur that converts Windows cursors to Xcursor while preserving image quality.";

  inputs = {
    nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.zst";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
  };

  outputs =
    inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      perSystem =
        { config, pkgs, ... }:
        let
          python = pkgs.python314;
        in
        {
          packages = {
            cursorgen = python.pkgs.callPackage ./pkgs/cursorgen.nix { };
            default = config.packages.cursorgen;
          };
          checks = { inherit (config.packages) cursorgen; };
          formatter = pkgs.nixfmt;
          devShells.default = pkgs.mkShell {
            packages = [
              (python.withPackages (
                ps:
                config.packages.cursorgen.dependencies
                ++ [
                  ps.black
                  ps.isort
                  ps.flake8
                  ps.mypy
                  ps.build
                  ps.hatchling
                  ps.pip
                ]
              ))
              pkgs.pre-commit
              config.formatter
              pkgs.actionlint
              pkgs.imagemagick
              pkgs.ffmpeg
            ];
          };
        };
    };
}
