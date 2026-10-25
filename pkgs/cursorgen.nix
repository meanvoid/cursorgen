{
  lib,
  buildPythonPackage,
  hatchling,
  numpy,
  opencv-python-headless,
  rich,
  typing-extensions,
  pythonOlder,
  unittestCheckHook,
}:

let
  project = (lib.importTOML ../pyproject.toml).project;
in
buildPythonPackage {
  pname = project.name;
  version = project.version;
  disabled = pythonOlder "3.7";
  pyproject = true;
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      (lib.fileset.fileFilter (file: file.hasExt "py") ../cursorgen)
      (lib.fileset.fileFilter (file: file.hasExt "py") ../tests)
      ../pyproject.toml
      ../README.md
      ../LICENSE
    ];
  };

  build-system = [ hatchling ];
  dependencies = [
    numpy
    opencv-python-headless
    rich
    typing-extensions
  ];

  nativeCheckInputs = [ unittestCheckHook ];
  unittestFlags = [
    "-s"
    "tests"
    "-v"
  ];

  pythonImportsCheck = [
    "cursorgen"
    "cursorgen.__main__"
    "cursorgen.parser"
    "cursorgen.writer"
  ];

  meta = {
    description = project.description;
    homepage = project.urls.Homepage;
    maintainers = [ lib.maintainers.ashuramaruzxc ];
    license = lib.licenses.gpl3Plus;
    mainProgram = "cursorgen";
  };
}
