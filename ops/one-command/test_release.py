"""Test the fail-closed decisions without a production daemon."""
import importlib.machinery
import importlib.util
import io
import json
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader("finanse_release", str(Path(__file__).with_name("finanse-release")))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
release = importlib.util.module_from_spec(spec)
loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_docs_and_tests_do_not_roll_out(self):
        self.assertFalse(release.application_scope(["docs/PLAN.md", "frontend/src/Foo.test.tsx"]))
        self.assertTrue(release.application_scope(["frontend/src/Foo.tsx"]))

    def test_sensitive_changes_require_the_manual_path(self):
        for path in ("backend/migrations/versions/a.py", "backend/app/config.py",
                     "backend/requirements.txt", "frontend/nginx.conf", ".github/workflows/ci.yml"):
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, "Manual release required"):
                release.application_scope(["frontend/src/Foo.tsx", path])

    def test_preserves_hardening_and_refuses_ambiguous_override(self):
        previous = "a" * 40
        candidate = {"images": {s: {"tag": f"local/finanse-{s}:" + "b" * 40} for s in release.SERVICES}}
        old = "services:\n" + "".join(f"  {s}:\n    image: local/finanse-{s}:{previous}\n"
                                     for s in release.SERVICES) + "    read_only: true\n"
        updated = release.app_override(old, previous, candidate)
        self.assertEqual(updated, old.replace(previous, "b" * 40))
        with self.assertRaisesRegex(RuntimeError, "Cannot preserve"):
            release.app_override(old + old, previous, candidate)

    def test_archive_refuses_unapproved_tag(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "images.tar.gz"
            data = json.dumps([{"RepoTags": ["unexpected:production"]}]).encode()
            with tarfile.open(path, "w:gz") as stream:
                member = tarfile.TarInfo("manifest.json")
                member.size = len(data)
                stream.addfile(member, io.BytesIO(data))
            with self.assertRaisesRegex(RuntimeError, "unapproved tags"):
                release.verify_archive(path, {"backend": {"tag": "expected:release"}})

    def test_rollback_uses_only_approved_images_and_checks_runtime(self):
        old = {name: {"tag": name + ":old", "id": "expected"} for name in release.SERVICES}
        stable = {"postgres": ["container", "image", "time"]}
        with (patch.object(release, "images") as pins,
              patch.object(release, "compose") as compose,
              patch.object(release, "wait_smoke") as smoke):
            release.restore_application({}, "/exact/old.yaml", old, stable)
            pins.assert_called_once_with(old)
            compose.assert_called_once_with({}, "/exact/old.yaml", "up", "-d", "--no-deps", "--no-build",
                                            "backend", "worker", "frontend", timeout=150)
            smoke.assert_called_once_with({}, old, stable)
            compose.reset_mock()
            pins.side_effect = RuntimeError("rollback image changed")
            with self.assertRaisesRegex(RuntimeError, "rollback image changed"):
                release.restore_application({}, "/exact/old.yaml", old, stable)
            compose.assert_not_called()
