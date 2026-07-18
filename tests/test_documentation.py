from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_DIR = Path(__file__).resolve().parent.parent
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
TRANSLATIONS = {
    "README.ar.md",
    "README.de.md",
    "README.es.md",
    "README.fr.md",
    "README.ja.md",
    "README.ko.md",
    "README.ru.md",
    "README.vi.md",
    "README.zh-Hans.md",
    "README.zh-Hant.md",
}


class DocumentationTests(unittest.TestCase):
    def test_all_local_markdown_links_resolve(self) -> None:
        failures: list[str] = []
        for document in REPO_DIR.rglob("*.md"):
            if "build" in document.parts or ".git" in document.parts:
                continue
            text = document.read_text(encoding="utf-8")
            for raw_target in MARKDOWN_LINK.findall(text):
                target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
                parsed = urlparse(target)
                if parsed.scheme or target.startswith("#"):
                    continue
                relative = unquote(parsed.path)
                destination = (document.parent / relative).resolve()
                if not destination.exists():
                    failures.append(
                        f"{document.relative_to(REPO_DIR)} -> {raw_target}"
                    )
        self.assertEqual([], failures)

    def test_language_selector_has_eleven_real_destinations(self) -> None:
        readme = (REPO_DIR / "README.md").read_text(encoding="utf-8")
        expected = {f"i18n/{name}" for name in TRANSLATIONS}
        expected.add("README.md")
        selector_targets = {
            target
            for target in MARKDOWN_LINK.findall(readme.split("</div>", 1)[0])
            if target == "README.md" or target.startswith("i18n/README.")
        }
        self.assertEqual(expected, selector_targets)
        actual = {
            path.name for path in (REPO_DIR / "i18n").glob("README.*.md")
        }
        self.assertEqual(TRANSLATIONS, actual)

    def test_release_handoff_has_required_update_controls(self) -> None:
        changelog = (REPO_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
        release = (REPO_DIR / "docs/releases/v0.1.0.md").read_text(
            encoding="utf-8"
        )
        handoff = (REPO_DIR / "docs/update-handoff.md").read_text(
            encoding="utf-8"
        )
        keyboard_handoff = (
            REPO_DIR / "docs/mobile-keyboard-parity-handoff.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## [0.1.0] - 2026-07-17", changelog)
        self.assertIn("git checkout v0.1.0", release)
        self.assertIn("--skip-account-login", release)
        self.assertIn("./scripts/verify.sh --quick", release)
        self.assertIn("git checkout 8a68200", release)
        self.assertIn("Copy-ready update message", handoff)
        self.assertIn("abcXYZ123,.!?", handoff)
        self.assertIn("Do not discard a dirty worktree", handoff)
        self.assertIn(
            "https://github.com/lachlanchen/uu-remote-ubuntu-bridge", handoff
        )
        self.assertNotIn("The private repository", handoff)
        self.assertNotIn("repository is private", release.lower())
        self.assertIn("OptiPlex-7090", keyboard_handoff)
        self.assertIn("v0.1.0", keyboard_handoff)
        self.assertIn("abcXYZ123,.!?", keyboard_handoff)
        self.assertIn("UURB_TEXT_KEY_DELAY_MS", keyboard_handoff)
        self.assertIn("Do not commit a completed record", keyboard_handoff)

    def test_xrdp_keyboard_recovery_preserves_safe_ordering(self) -> None:
        recovery = (
            REPO_DIR / "docs/xrdp-and-keyboard-recovery.md"
        ).read_text(encoding="utf-8")

        self.assertIn("reset the controller application first", recovery)
        self.assertIn("--physical-key-delay-ms 8", recovery)
        self.assertIn("--physical-key-delay-ms 0", recovery)
        self.assertIn("1620x1080", recovery)
        self.assertIn("subtype:0", recovery)
        self.assertIn("does not prove", recovery)
        self.assertIn("never record a key code", recovery)


if __name__ == "__main__":
    unittest.main()
