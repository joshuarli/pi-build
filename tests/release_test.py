import gzip
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.release import TARGETS, main, merge, object_mapping, write

REVISION = "a" * 40
COMPANIONS = {
    "agent-intercom-claude": "0.10.0",
    "agent-intercom-codex": "0.10.0",
    "agent-intercom-opencode": "0.10.0",
}


class FixturePart(TypedDict):
    schema: int
    builder_revision: str
    profile: str
    product: str
    version: str
    sources_sha256: str
    components: dict[str, str]
    companions: dict[str, dict[str, str | int]]
    targets: dict[str, dict[str, str | int]]
    inputs: dict[str, object]


def write_companions(assets: Path) -> dict[str, dict[str, str | int]]:
    companions: dict[str, dict[str, str | int]] = {}
    for name, version in COMPANIONS.items():
        member = tarfile.TarInfo("package/package.json")
        payload = json.dumps({"name": name, "version": version}).encode()
        member.size = len(payload)
        member.mtime = 0
        buffer = io.BytesIO()
        with (
            gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as bundle,
        ):
            bundle.addfile(member, io.BytesIO(payload))
        archive = assets / f"{name}-{version}.tgz"
        archive.write_bytes(buffer.getvalue())
        companions[name] = {
            "archive": archive.name,
            "version": version,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "bytes": archive.stat().st_size,
            "source_sha": "c" * 40,
        }
    return companions


def part(assets: Path, target: str, revision: str = REVISION, profile: str = "full") -> FixturePart:
    archive = assets / f"pi-{profile}-1.5.0-{target}.tar.xz"
    archive.write_bytes(target.encode())
    sha256 = hashlib.sha256(target.encode()).hexdigest()
    (assets / f"pi-{profile}-1.5.0-{target}.manifest.json").write_text(json.dumps({"sha256": sha256, "source_revision": revision}))
    return {
        "schema": 1, "builder_revision": revision, "profile": profile, "product": f"pi-{profile}", "version": "1.5.0",
        "sources_sha256": "s", "components": {"c": "x"}, "companions": write_companions(assets),
        "targets": {target: {"target": target, "profile": profile, "archive": archive.name, "sha256": sha256, "bytes": len(target)}},
        "inputs": {target: {"lock_sha256": target}},
    }


class ReleaseTests(unittest.TestCase):
    def test_headless_release_retains_its_profile_identity(self):
        merged = merge(self.assets, [part(self.assets, target, profile="headless-usr") for target in TARGETS])
        self.assertEqual(merged["product"], "pi-headless-usr")
        self.assertEqual(merged["profile"], "headless-usr")
        self.assertTrue(all(record["archive"].startswith("pi-headless-usr-") for record in merged["targets"].values()))

    def setUp(self):
        Path(".work/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=".work/tmp")
        self.assets = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def test_merged_assets_satisfy_the_consumer_identity_checks(self):
        merged = merge(self.assets, [part(self.assets, target) for target in TARGETS])
        write(self.assets, merged)
        provenance = json.loads((self.assets / "provenance.json").read_text())
        sums = [line.split() for line in (self.assets / "SHA256SUMS").read_text().splitlines()]
        for target in TARGETS:
            record = provenance["targets"][target]
            self.assertEqual(provenance["builder_revision"], REVISION)
            self.assertEqual(set(record), {"target", "profile", "archive", "sha256", "bytes"})
            self.assertEqual([entry for entry in sums if entry[1] == record["archive"]], [[record["sha256"], record["archive"]]])
        self.assertEqual([entry[1] for entry in sums], sorted(path.name for path in self.assets.iterdir() if path.name != "SHA256SUMS"))

    def test_release_command_requires_an_input(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(main(["tools/release.py", str(self.assets)]), 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Usage: python3 -I tools/release.py ASSET_DIR PROVENANCE...", stderr.getvalue())
        self.assertEqual(list(self.assets.iterdir()), [])

    def test_release_command_writes_the_outputs_and_reports_provenance_digest(self):
        for combined in (False, True):
            with self.subTest(combined=combined), tempfile.TemporaryDirectory(dir=self.assets.parent) as scratch:
                root = Path(scratch)
                assets = root / "assets"
                assets.mkdir()
                parts = [part(assets, target) for target in TARGETS]
                if combined:
                    for record in parts[1:]:
                        parts[0]["targets"].update(record["targets"])
                        parts[0]["inputs"].update(record["inputs"])
                    parts = parts[:1]
                inputs = []
                for index, record in enumerate(parts):
                    path = root / f"part-{index}.json"
                    path.write_text(json.dumps(record))
                    inputs.append(str(path))
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(main(["tools/release.py", str(assets), *inputs]), 0)
                self.assertEqual(stderr.getvalue(), "")
                provenance = assets / "provenance.json"
                payload = provenance.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                self.assertEqual(stdout.getvalue(), f"ok: release provenance {digest}\n")
                self.assertEqual(set(json.loads(payload)["targets"]), set(TARGETS))
                self.assertIn(f"{digest}  provenance.json", (assets / "SHA256SUMS").read_text())

    def test_provenance_mapping_rejects_non_object_or_non_string_key(self):
        for value in ([], {1: "value"}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "^expected JSON object$"):
                object_mapping(value)

    def test_rejects_incorrect_target_record_field_types(self):
        target = TARGETS[0]
        for field, value in (("target", 1), ("profile", None), ("archive", 1), ("sha256", 1), ("bytes", True)):
            with self.subTest(field=field):
                release_part = part(self.assets, target)
                original = release_part["targets"][target]
                malformed = release_part | {"targets": {target: original | {field: value}}}
                with self.assertRaisesRegex(ValueError, f"^invalid target record {target}$"):
                    merge(self.assets, [malformed])

    def test_preserves_opaque_input_metadata_and_serialized_shape(self):
        parts = [part(self.assets, target) for target in TARGETS]
        parts[0]["inputs"][TARGETS[0]] = {"nested": [None, True, 42, {"arbitrary": "value"}]}
        expected = {key: value for key, value in parts[0].items() if key not in ("targets", "inputs")}
        expected["targets"] = {target: part["targets"][target] for target, part in zip(TARGETS, parts)}
        expected["inputs"] = {target: part["inputs"][target] for target, part in zip(TARGETS, parts)}
        write(self.assets, merge(self.assets, parts))
        self.assertEqual((self.assets / "provenance.json").read_text(), json.dumps(expected, indent=2, sort_keys=True) + "\n")

    def test_rejects_unknown_provenance_envelope(self):
        with self.assertRaisesRegex(ValueError, "^no provenance inputs$"):
            merge(self.assets, [])
        release_part = part(self.assets, TARGETS[0])
        with self.assertRaisesRegex(ValueError, "^unsupported provenance schema$"):
            merge(self.assets, [release_part | {"schema": 2}])
        with self.assertRaisesRegex(TypeError, "^invalid provenance identity$"):
            merge(self.assets, [release_part | {"builder_revision": None}])

    def test_reports_the_inconsistent_target(self):
        target = TARGETS[0]
        release_part = part(self.assets, target)
        with self.assertRaisesRegex(ValueError, f"^duplicate target {target}$"):
            merge(self.assets, [release_part, release_part])
        record = release_part["targets"][target]
        record["target"] = TARGETS[1]
        with self.assertRaisesRegex(ValueError, f"^invalid target record {target}$"):
            merge(self.assets, [release_part])
        record["target"] = target
        record["archive"] = "unexpected.tar.xz"
        with self.assertRaisesRegex(ValueError, f"^unexpected archive name for {target}$"):
            merge(self.assets, [release_part])

    def test_rejects_targets_built_at_different_revisions(self):
        parts = [part(self.assets, target) for target in TARGETS[:2]] + [part(self.assets, TARGETS[2], "b" * 40)]
        with self.assertRaisesRegex(ValueError, "builder_revision differs"):
            merge(self.assets, parts)

    def test_rejects_incomplete_target_set(self):
        with self.assertRaisesRegex(ValueError, f"^release requires targets {', '.join(TARGETS)}$"):
            merge(self.assets, [part(self.assets, target) for target in TARGETS[:2]])

    def test_rejects_archive_that_differs_from_its_record(self):
        parts = [part(self.assets, target) for target in TARGETS]
        (self.assets / "pi-full-1.5.0-x86_64-unknown-linux-musl.tar.xz").write_bytes(b"tampered!")
        with self.assertRaisesRegex(ValueError, "mismatch for x86_64-unknown-linux-musl"):
            merge(self.assets, parts)

    def test_rejects_manifest_that_differs_from_its_archive_record(self):
        parts = [part(self.assets, target) for target in TARGETS]
        (self.assets / "pi-full-1.5.0-aarch64-apple-darwin.manifest.json").write_text(json.dumps({"sha256": "0" * 64, "source_revision": REVISION}))
        with self.assertRaisesRegex(ValueError, "manifest differs from provenance for aarch64-apple-darwin"):
            merge(self.assets, parts)

    def test_rejects_archive_size_or_digest_mismatch_independently(self):
        for field in ("bytes", "sha256"):
            with self.subTest(field=field):
                parts = [part(self.assets, target) for target in TARGETS]
                record = parts[0]["targets"][TARGETS[0]]
                record[field] = 1 if field == "bytes" else "0" * 64
                with self.assertRaisesRegex(ValueError, "archive digest or size mismatch"):
                    merge(self.assets, parts)

    def test_rejects_symlinked_target_assets(self):
        for suffix in ("tar.xz", "manifest.json"):
            with self.subTest(suffix=suffix):
                parts = [part(self.assets, target) for target in TARGETS]
                path = self.assets / f"pi-full-1.5.0-{TARGETS[0]}.{suffix}"
                original = path.with_name(f"original-{suffix}")
                path.rename(original)
                path.symlink_to(original.name)
                with self.assertRaisesRegex(ValueError, "missing (archive|manifest)"):
                    merge(self.assets, parts)
                path.unlink()
                original.unlink()

    def test_rejects_invalid_companion_metadata(self):
        for field, value in (("archive", 1), ("version", 1), ("extra", "x"), ("bytes", True)):
            with self.subTest(field=field):
                parts = [part(self.assets, target) for target in TARGETS]
                for item in parts:
                    item["companions"]["agent-intercom-claude"][field] = value
                with self.assertRaisesRegex(ValueError, "invalid companion (record|size)"):
                    merge(self.assets, parts)

    def companion_release(self):
        parts = [part(self.assets, target) for target in TARGETS]
        companions = parts[0]["companions"]
        for package in parts:
            package["companions"] = companions
        name = "agent-intercom-claude"
        return parts, name, companions[name], self.assets / f"{name}-{COMPANIONS[name]}.tgz"

    def test_rejects_missing_symlinked_or_nested_companion_archive(self):
        for representation in ("missing", "symlinked", "nested"):
            with self.subTest(representation=representation):
                parts, _, record, archive = self.companion_release()
                if representation == "missing":
                    archive.unlink()
                elif representation == "symlinked":
                    original = archive.with_suffix(".original")
                    archive.rename(original)
                    archive.symlink_to(original.name)
                else:
                    directory = self.assets / "nested"
                    directory.mkdir()
                    archive.rename(directory / archive.name)
                    record["archive"] = f"nested/{archive.name}"
                try:
                    with self.assertRaisesRegex(ValueError, "^missing companion archive .*agent-intercom-claude"):
                        merge(self.assets, parts)
                finally:
                    if archive.is_symlink():
                        archive.unlink()

    def test_rejects_companion_size_or_digest_mismatch_independently(self):
        for field, wrong_value in (("bytes", 0), ("bytes", 1), ("sha256", "0" * 64)):
            with self.subTest(field=field, wrong_value=wrong_value):
                parts, name, record, _ = self.companion_release()
                record[field] = wrong_value
                if wrong_value == 0:
                    diagnostic = f"^invalid companion size {name}$"
                else:
                    diagnostic = f"^companion archive digest or size mismatch: {name}$"
                with self.assertRaisesRegex(ValueError, diagnostic):
                    merge(self.assets, parts)

    def test_companion_requires_a_nonempty_gzip_tar(self):
        for mode in ("w", "w:gz"):
            with self.subTest(mode=mode):
                parts, name, record, archive = self.companion_release()
                with tarfile.open(archive, mode) as bundle:
                    if mode == "w":
                        bundle.addfile(tarfile.TarInfo("package/README.md"))
                data = archive.read_bytes()
                record["bytes"] = len(data)
                record["sha256"] = hashlib.sha256(data).hexdigest()
                if mode == "w":
                    with self.assertRaises(tarfile.ReadError):
                        merge(self.assets, parts)
                else:
                    with self.assertRaisesRegex(ValueError, f"^companion archive is empty: {name}$"):
                        merge(self.assets, parts)

    def test_companion_archive_member_names_must_be_relative_and_normalized(self):
        for member_name in ("/package/README.md", "package/docs/../README.md"):
            with self.subTest(member=member_name):
                parts, name, record, archive = self.companion_release()
                with (
                    gzip.GzipFile(filename=str(archive), mode="wb", mtime=0) as compressed,
                    tarfile.open(fileobj=compressed, mode="w") as bundle,
                ):
                    bundle.addfile(tarfile.TarInfo(member_name))
                data = archive.read_bytes()
                record["bytes"] = len(data)
                record["sha256"] = hashlib.sha256(data).hexdigest()
                with self.assertRaises(ValueError) as error:
                    merge(self.assets, parts)
                self.assertEqual(str(error.exception), f"companion archive has unsafe member {member_name}: {name}")

    def test_rejects_missing_companion_kind(self):
        parts = [part(self.assets, target) for target in TARGETS]
        for item in parts:
            del item["companions"]["agent-intercom-claude"]
        with self.assertRaisesRegex(ValueError, f"^release requires companions {', '.join(COMPANIONS)}$"):
            merge(self.assets, parts)

    def test_rejects_target_record_with_extra_identity_fields(self):
        parts = [part(self.assets, target) for target in TARGETS]
        parts[0]["targets"]["aarch64-apple-darwin"]["builder_revision"] = REVISION
        with self.assertRaisesRegex(ValueError, "invalid target record"):
            merge(self.assets, parts)

    def test_rejects_target_record_with_non_string_archive(self):
        parts = [part(self.assets, target) for target in TARGETS]
        parts[0]["targets"][TARGETS[0]]["archive"] = 1
        with self.assertRaisesRegex(ValueError, "invalid target record"):
            merge(self.assets, parts)

    def test_rejects_non_string_shared_identity(self):
        part_with_bad_identity: dict[str, object] = dict(part(self.assets, TARGETS[0]))
        part_with_bad_identity["product"] = 1
        with self.assertRaisesRegex(TypeError, "invalid provenance identity"):
            merge(self.assets, [part_with_bad_identity])


if __name__ == "__main__":
    unittest.main()
