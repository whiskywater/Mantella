# Mantella packaged build

Build with a Windows Python environment that has Tk enabled. From the source
root, run:

```powershell
python scripts/validate_packaging_environment.py
python -m PyInstaller --clean packaging/Mantella.spec --distpath build/dist --workpath build/work
python scripts/run_packaged_startup_smoke.py --exe build/dist/Mantella/Mantella.exe --working-dir build/dist/Mantella --probe-mantella-init
```

The deployable artifact is the complete `build/dist/Mantella` directory. It
contains `Mantella.exe` and its matching `_internal` directory; copying the
executable alone is unsupported and can pair incompatible embedded Python
runtimes. The preflight intentionally fails when Tk is unavailable. The spec
collects `gradio` and `gradio_client` package data/modules because their UI
startup path performs dynamic imports and reads JSON metadata.
The build gate also POSTs the real `/mantella` initialize route after UI
readiness. This constructs the production `LLMClient`, including tokenizer
initialization, so a package that only serves `/ui` is rejected.
