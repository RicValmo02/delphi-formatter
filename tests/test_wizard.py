"""End-to-end tests for the interactive wizard.

The wizard reads from *stdin* and writes to *stdout*, both injected, so we
drive it with scripted ``io.StringIO`` input and assert on the resulting JSON
config and/or on the captured output.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from delphi_formatter.config import default_config  # noqa: E402
from delphi_formatter.wizard import (  # noqa: E402
    PROFILES,
    PREVIEW_SNIPPET,
    run_wizard,
    _profile_minimal,
    _profile_vcl_hungarian,
)


def _run(script: str, output_path: Path, **kwargs) -> tuple[int, str]:
    """Run the wizard against a scripted stdin, return (exit_code, stdout)."""
    stdin = io.StringIO(script)
    stdout = io.StringIO()
    rc = run_wizard(
        output_path, stdin=stdin, stdout=stdout, **kwargs
    )
    return rc, stdout.getvalue()


class WizardProfilesTests(unittest.TestCase):
    def test_minimal_profile_save_immediately(self) -> None:
        """Profile 1 + 'no, don't refine' should save the Minimal profile as-is."""
        # 1) pick profile 1 (Minimal)
        # 2) "Refine section by section?" -> n
        script = "1\nn\n"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _captured = _run(script, out)
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            with out.open() as f:
                saved = json.load(f)
            # Minimal == default_config() exactly
            self.assertEqual(saved, _profile_minimal())
            self.assertEqual(saved, default_config())

    def test_vcl_hungarian_profile_matches_helper(self) -> None:
        """Profile 3 (VCL Hungarian) + save -> matches _profile_vcl_hungarian()."""
        script = "3\nn\n"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _captured = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
            self.assertEqual(saved, _profile_vcl_hungarian())
            self.assertTrue(saved["variablePrefix"]["local"]["enabled"])
            self.assertTrue(saved["variablePrefix"]["classField"]["enabled"])
            self.assertTrue(saved["variablePrefix"]["byType"]["enabled"])

    def test_default_profile_on_empty_input(self) -> None:
        """Bare Enter on the profile prompt selects profile 1 (Minimal)."""
        # empty line for profile (-> default 1), then 'n' to skip refine
        script = "\nn\n"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _ = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
            self.assertEqual(saved, _profile_minimal())

    def test_all_profiles_listed_in_banner(self) -> None:
        script = "1\nn\n"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            _rc, captured = _run(script, out)
        for name, _desc, _fn in PROFILES:
            self.assertIn(name, captured)


class WizardByTypeSubloopTests(unittest.TestCase):
    """The byType sub-loop is the key user-requested feature."""

    def _save_exit_suffix(self) -> str:
        # 12 = Save & exit in the main menu (11 sections + Save)
        return "12\n"

    def test_add_rule_via_subloop(self) -> None:
        # Start from Minimal, refine, go to section 6 (byType), enable,
        # keep default conflict resolution, keep skipVisualComponents at
        # its default (safe), add rule TTimer -> tmr, done, Save & exit.
        script = "\n".join([
            "1",          # Minimal profile
            "y",          # refine
            "6",          # section: byType
            "y",          # enable
            "",           # conflictResolution default
            "",           # skipVisualComponents default (true)
            "a",          # action: add
            "TTimer",     # typePattern
            "tmr",        # prefix
            "d",          # done with byType
            "12",         # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _ = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
        rules = saved["variablePrefix"]["byType"]["rules"]
        self.assertTrue(any(
            r["typePattern"] == "TTimer" and r["prefix"] == "tmr"
            for r in rules
        ))

    def test_remove_rule_via_subloop(self) -> None:
        # VCL Hungarian has 10 default rules; remove rule #1 (TButton) and verify.
        script = "\n".join([
            "3",          # VCL Hungarian
            "y",          # refine
            "6",          # byType section
            "",           # keep enabled=Y default
            "",           # keep default conflictResolution
            "",           # keep skipVisualComponents default
            "r",          # remove
            "1",          # rule number 1 (TButton)
            "d",          # done
            "12",         # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _ = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
        rules = saved["variablePrefix"]["byType"]["rules"]
        self.assertFalse(
            any(r["typePattern"] == "TButton" for r in rules),
            f"TButton should have been removed, rules={rules}",
        )

    def test_invalid_regex_is_rejected_and_reprompted(self) -> None:
        """An unbalanced regex must be refused, then a valid one accepted."""
        script = "\n".join([
            "1",            # Minimal
            "y",            # refine
            "6",            # byType
            "y",            # enable
            "",             # default conflictResolution
            "",             # skipVisualComponents default
            "a",            # add
            "T(unclosed",   # BAD regex
            "TFoo",         # OK regex
            "foo",          # prefix
            "d",            # done
            "12",           # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, captured = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
        self.assertIn("invalid regex", captured)
        self.assertIn(
            {"typePattern": "TFoo", "prefix": "foo"},
            saved["variablePrefix"]["byType"]["rules"],
        )

    def test_invalid_pascal_prefix_is_rejected(self) -> None:
        script = "\n".join([
            "1",          # Minimal
            "y",          # refine
            "6",          # byType
            "y",          # enable
            "",           # default conflictResolution
            "",           # skipVisualComponents default
            "a",          # add
            "TFoo",       # regex
            "123bad",     # invalid pascal ident
            "foo",        # valid
            "d",          # done
            "12",         # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, captured = _run(script, out)
            self.assertEqual(rc, 0)
        self.assertIn("not a valid Pascal identifier", captured)


class WizardSkipVisualComponentsTests(unittest.TestCase):
    """The form-safety prompt only fires when classField or byType is enabled."""

    def test_prompt_defaults_to_true_through_field_prefix(self) -> None:
        # Start from Minimal, refine, go to section 4 (class-field prefix),
        # enable it, keep default prefix + capitalize + skipVisualComponents.
        script = "\n".join([
            "1",          # Minimal
            "y",          # refine
            "4",          # class-field prefix section
            "y",          # enable classField
            "",           # default prefix = 'F'
            "",           # default capitalize = yes
            "",           # skipVisualComponents default (true)
            "12",         # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _ = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
        self.assertTrue(saved["variablePrefix"]["skipVisualComponents"])

    def test_prompt_can_opt_out(self) -> None:
        script = "\n".join([
            "1",          # Minimal
            "y",          # refine
            "4",          # class-field prefix
            "y",          # enable classField
            "",           # default prefix
            "",           # default capitalize
            "n",          # NO, don't skip form classes — we want the sync on
            "12",         # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _ = _run(script, out)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
        self.assertFalse(saved["variablePrefix"]["skipVisualComponents"])
        # Internal wizard marker must NOT leak into the saved config.
        self.assertNotIn("_skipVisualComponents_asked", saved["variablePrefix"])

    def test_not_asked_when_no_rename_features_enabled(self) -> None:
        # If the user never enables classField/byType, the prompt isn't fired.
        # We verify this by NOT supplying an answer for it — the wizard would
        # hang otherwise, and the test would deadlock.
        script = "\n".join([
            "1",          # Minimal
            "y",          # refine
            "4",          # class-field prefix section
            "n",          # decline classField
            "12",         # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, _ = _run(script, out)
            self.assertEqual(rc, 0)


class WizardPreviewTests(unittest.TestCase):
    def test_preview_shows_formatted_output(self) -> None:
        # Minimal + refine + section 11 (Preview) + back to menu + Save & exit
        script = "\n".join([
            "1",        # Minimal
            "y",        # refine
            "11",       # Preview on sample
            "12",       # Save & exit
            "",
        ])
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            rc, captured = _run(script, out)
            self.assertEqual(rc, 0)
        # Preview prints both the raw input and the formatted block.
        self.assertIn("--- input ---", captured)
        self.assertIn("--- formatted with current config ---", captured)
        # Sanity: a token from the snippet appears in captured output.
        self.assertIn("TDemo", captured)


class WizardOverwriteTests(unittest.TestCase):
    def test_existing_file_without_force_asks_for_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            out.write_text("{}", encoding="utf-8")
            # 1=Minimal, n=don't refine, then "n" to refuse overwrite
            script = "1\nn\nn\n"
            rc, captured = _run(script, out)
            self.assertEqual(rc, 1)
            self.assertIn("aborted", captured.lower())
            # File content unchanged
            self.assertEqual(out.read_text(encoding="utf-8"), "{}")

    def test_existing_file_with_force_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "cfg.json"
            out.write_text("{}", encoding="utf-8")
            script = "1\nn\n"
            rc, _ = _run(script, out, force=True)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
            self.assertEqual(saved, default_config())


class WizardFromExistingFileTests(unittest.TestCase):
    def test_from_path_is_deep_merged_on_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "existing.json"
            src.write_text(
                json.dumps({"keywords": {"case": "upper"}}), encoding="utf-8"
            )
            out = Path(td) / "out.json"
            # no profile prompt because --from is set; just "don't refine"
            script = "n\n"
            rc, _ = _run(script, out, from_path=src)
            self.assertEqual(rc, 0)
            with out.open() as f:
                saved = json.load(f)
            self.assertEqual(saved["keywords"]["case"], "upper")
            # Defaults still present for unset sections
            self.assertEqual(saved["indent"]["size"], 2)


class WizardSnippetTests(unittest.TestCase):
    def test_preview_snippet_is_valid_delphi_ish_text(self) -> None:
        # Just a smoke test: non-empty, has BEGIN/END markers.
        self.assertTrue(PREVIEW_SNIPPET.strip())
        self.assertIn("BEGIN", PREVIEW_SNIPPET)
        self.assertIn("END", PREVIEW_SNIPPET)


if __name__ == "__main__":
    unittest.main()
