import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config, load_config
from delphi_formatter.formatter import format_source


class EndToEndTests(unittest.TestCase):
    def test_sample_file_formats_without_error(self) -> None:
        src = (ROOT / "examples" / "input_sample.pas").read_text(encoding="utf-8")
        cfg = load_config(ROOT / "delphi-formatter.json")
        out = format_source(src, cfg)
        self.assertIsInstance(out, str)
        self.assertGreater(len(out), 0)
        # Keywords should now be lowercase (per default config)
        self.assertIn("unit Sample", out)
        self.assertIn("implementation", out)
        self.assertIn("end.", out)

    def test_idempotent(self) -> None:
        src = (ROOT / "examples" / "input_sample.pas").read_text(encoding="utf-8")
        cfg = load_config(ROOT / "delphi-formatter.json")
        once = format_source(src, cfg)
        twice = format_source(once, cfg)
        self.assertEqual(once, twice, "formatter should be idempotent")

    def test_type_prefix_applied_to_sample(self) -> None:
        src = (ROOT / "examples" / "input_sample.pas").read_text(encoding="utf-8")
        cfg = load_config(ROOT / "delphi-formatter.json")
        out = format_source(src, cfg)
        # TButton fields/locals get the 'btn' prefix
        self.assertIn("btn", out)
        # TStringList gets 'sl'
        self.assertIn("sl", out)

    def test_cli_format_subcommand(self) -> None:
        """Invoke the module as a script to verify CLI wiring."""
        result = subprocess.run(
            [sys.executable, "-m", "delphi_formatter", "format",
             str(ROOT / "examples" / "input_sample.pas"),
             "--config", str(ROOT / "delphi-formatter.json")],
            cwd=str(ROOT),
            env={**_env_with_src(), "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("unit Sample", result.stdout)

    def test_cli_check_reports_needs_format(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "delphi_formatter", "check",
             str(ROOT / "examples" / "input_sample.pas"),
             "--config", str(ROOT / "delphi-formatter.json")],
            cwd=str(ROOT),
            env={**_env_with_src(), "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        # The sample is intentionally unformatted, so check should exit 1
        self.assertEqual(result.returncode, 1)


def _env_with_src() -> dict:
    import os
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    sep = ";" if sys.platform.startswith("win") else ":"
    env["PYTHONPATH"] = f"{SRC}{sep}{existing}" if existing else str(SRC)
    return env


if __name__ == "__main__":
    unittest.main()
