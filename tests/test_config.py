import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import (
    default_config,
    load_config,
    save_config,
    validate_config,
)


class ConfigTests(unittest.TestCase):
    def test_default_is_valid(self) -> None:
        errs = validate_config(default_config())
        self.assertEqual(errs, [])

    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cfg.json"
            save_config(default_config(), path)
            loaded = load_config(path)
            self.assertEqual(loaded, default_config())

    def test_deep_merge_preserves_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cfg.json"
            path.write_text(json.dumps({"keywords": {"case": "upper"}}), encoding="utf-8")
            loaded = load_config(path)
            # Overridden
            self.assertEqual(loaded["keywords"]["case"], "upper")
            # Untouched defaults present
            self.assertEqual(loaded["indent"]["size"], 2)
            self.assertIn("byType", loaded["variablePrefix"])

    def test_validation_catches_bad_case(self) -> None:
        cfg = default_config()
        cfg["keywords"]["case"] = "weird"
        errs = validate_config(cfg)
        self.assertTrue(any("keywords.case" in e for e in errs))

    def test_validation_catches_bad_indent(self) -> None:
        cfg = default_config()
        cfg["indent"]["style"] = "wat"
        errs = validate_config(cfg)
        self.assertTrue(any("indent.style" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
