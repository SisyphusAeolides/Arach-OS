#!/usr/bin/env python3
import os
from pathlib import Path
import tempfile
import unittest

from repository import (
    CatalogRepositoryError,
    OFFLINE_CATALOG_ROOT,
    REPOSITORY_KEYRING,
    catalog_paths,
    load_repository_configuration,
    remap_catalog_file,
)


class RepositoryConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="arach-hwd-repository-")
        self.root = Path(self.temporary.name)
        self.configuration = self.root / "repository.toml"

    def tearDown(self):
        self.temporary.cleanup()

    def write_configuration(self, **changes):
        values = {
            "format": 1,
            "manifest_url": "https://hardware.example.invalid/catalog.toml",
            "signature_url": "https://hardware.example.invalid/catalog.toml.sig",
            "keyring": str(REPOSITORY_KEYRING),
            "required": True,
        }
        values.update(changes)
        self.configuration.write_text(
            "\n".join(
                [
                    f"format = {values['format']}",
                    f"manifest_url = \"{values['manifest_url']}\"",
                    f"signature_url = \"{values['signature_url']}\"",
                    f"keyring = \"{values['keyring']}\"",
                    f"required = {'true' if values['required'] else 'false'}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_missing_configuration_disables_remote_sync(self):
        self.assertIsNone(load_repository_configuration(self.configuration))

    def test_exact_https_configuration_is_accepted(self):
        self.write_configuration(required=False)
        loaded = load_repository_configuration(self.configuration)
        self.assertEqual(loaded.keyring, REPOSITORY_KEYRING)
        self.assertFalse(loaded.required)
        self.assertTrue(loaded.manifest_url.startswith("https://"))

    def test_http_credentials_fragments_and_wrong_keyring_are_rejected(self):
        for field, value in [
            ("manifest_url", "http://hardware.example.invalid/catalog.toml"),
            ("manifest_url", "https://user@hardware.example.invalid/catalog.toml"),
            ("signature_url", "https://hardware.example.invalid/catalog.sig#latest"),
            ("keyring", "/tmp/unmeasured-keys.toml"),
        ]:
            with self.subTest(field=field, value=value):
                self.write_configuration(**{field: value})
                with self.assertRaises(CatalogRepositoryError):
                    load_repository_configuration(self.configuration)

    def test_unknown_fields_symlinks_and_oversized_files_are_rejected(self):
        self.write_configuration()
        with self.configuration.open("a", encoding="utf-8") as stream:
            stream.write("extra = true\n")
        with self.assertRaises(CatalogRepositoryError):
            load_repository_configuration(self.configuration)

        self.configuration.unlink()
        target = self.root / "target.toml"
        target.write_text("format = 1\n", encoding="utf-8")
        os.symlink(target, self.configuration)
        with self.assertRaises(CatalogRepositoryError):
            load_repository_configuration(self.configuration)

        self.configuration.unlink()
        self.configuration.write_bytes(b"x" * (64 * 1024 + 1))
        with self.assertRaises(CatalogRepositoryError):
            load_repository_configuration(self.configuration)

    def test_catalog_paths_and_metadata_remapping_are_confined(self):
        active = catalog_paths(Path("/run/arach-installer/catalog"))
        self.assertEqual(active.profiles, Path("/run/arach-installer/catalog/profiles"))
        mapped = remap_catalog_file(
            str(OFFLINE_CATALOG_ROOT / "driver-sources/modules.alias"),
            active.root,
        )
        self.assertEqual(
            mapped,
            Path("/run/arach-installer/catalog/driver-sources/modules.alias"),
        )
        with self.assertRaises(CatalogRepositoryError):
            remap_catalog_file("/tmp/modules.alias", active.root)
        with self.assertRaises(CatalogRepositoryError):
            catalog_paths(Path("relative/catalog"))


if __name__ == "__main__":
    unittest.main()
