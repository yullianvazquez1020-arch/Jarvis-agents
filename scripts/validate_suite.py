"""Validate an integration with real dependencies, Redis, and no skipped tests."""
from __future__ import annotations

import importlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    expected = {"faster-whisper": "1.2.1", "onnxruntime": "1.30.0", "av": "16.1.0"}
    for package, version in expected.items():
        actual = importlib.metadata.version(package)
        if actual != version:
            raise RuntimeError(f"{package}: expected {version}, found {actual}")
    for module in ("faster_whisper", "onnxruntime", "av"):
        importlib.import_module(module)
    if not shutil.which("redis-server"):
        raise RuntimeError("redis-server is required: Redis tests must not be skipped")
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    summary = {
        "tests": result.testsRun,
        "failures": [test.id() for test, _ in result.failures],
        "errors": [test.id() for test, _ in result.errors],
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "dependencies": expected,
    }
    print(json.dumps(summary, ensure_ascii=False))
    # A green check must not conceal missing dependencies or a truncated discovery.
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun >= 579 else 1


if __name__ == "__main__":
    raise SystemExit(main())
