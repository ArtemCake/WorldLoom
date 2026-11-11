# tests/python/web/test_web_assets.py

"""Проверки связи манифеста Vite с публичными ресурсами."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.web.assets import create_static_url, static_url


class WebAssetsTests(unittest.TestCase):
    """Проверки на изолированном временном каталоге сборки."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.dist = Path(self.directory.name)
        self.manifest_file = self.dist / ".vite" / "manifest.json"
        self.manifest_file.parent.mkdir(parents=True)

        self.js_path = "assets/js/main-a1b2c3.js"
        self.css_path = "assets/css/styles-d4e5f6.css"

        for relative in (self.js_path, self.css_path):
            target = self.dist / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")

        self.manifest = {
            "src/js/main.js": {"file": self.js_path},
            "src/styles/style.scss": {"file": self.css_path},
        }
        self.write_manifest()

    def write_manifest(self) -> None:
        self.manifest_file.write_text(
            json.dumps(self.manifest),
            encoding="utf-8",
        )

    def test_legacy_names_resolve_to_hashed_files(self) -> None:
        resolve = create_static_url(self.manifest_file)

        self.assertEqual(
            resolve("js/main.min.js"),
            f"/frontend/public/{self.js_path}",
        )
        self.assertEqual(
            resolve("css/style.min.css"),
            f"/frontend/public/{self.css_path}",
        )

    def test_renaming_entry_without_manifest_update_is_rejected(self) -> None:
        original = self.dist / self.js_path
        original.rename(original.with_name("main.min.js"))

        with self.assertRaises(RuntimeError):
            create_static_url(self.manifest_file)

    def test_missing_stylesheet_entry_is_rejected(self) -> None:
        del self.manifest["src/styles/style.scss"]
        self.write_manifest()

        with self.assertRaises(RuntimeError):
            create_static_url(self.manifest_file)

    def test_unsafe_public_paths_are_rejected(self) -> None:
        paths = (
            "../private/map.png",
            "/assets/main.js",
            "assets/../main.js",
            "private/map.png",
            "assets/main.js?version=1",
        )

        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    static_url(path)


if __name__ == "__main__":
    unittest.main()
