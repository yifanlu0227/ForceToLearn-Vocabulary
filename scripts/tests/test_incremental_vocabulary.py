from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_vocabulary as wire
from incremental_vocabulary import ENTRY_FIELDS, compile_sources, load_json, normalized_term, prepare_incremental_release
from publish_vocabulary import CommandError, Releases, command, publish_repository


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(wire.json_text(value), encoding="utf-8")


def entry(entry_id="rain-date", term="rain date"):
    return {"id": entry_id, "term": term, "partsOfSpeech": ["noun"], "definitionZh": "雨天备用日期",
            "explanationZh": "户外活动提前安排的雨天备用日期。",
            "examples": [{"en": "The rain date is Sunday.", "zh": "雨天改到周日。", "scenarioZh": "活动通知"}],
            "usageNotesZh": ["活动通知中常见。"], "tags": ["events"]}


def batch(entries=None, batch_id="life-new", date="2026-10-10"):
    return {"schemaVersion": 1, "batchId": batch_id, "title": "日常生活", "publishedOn": date,
            "entries": [entry()] if entries is None else entries}


def initialize(root):
    fixture = json.loads((Path(__file__).parent / "fixtures/baseline.json").read_text())
    fixture.update(contentVersion=3, updatedOn="2026-10-08")
    source = root / "baseline/vocabulary-v3.json"
    write(source, fixture)
    wire.prepare_release(source, root, catalog=fixture)
    return fixture


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="force-vocab-test-")
        self.root = Path(self.temporary.name) / "source"
        self.baseline = initialize(self.root)
        self.output = Path(self.temporary.name) / "output"
        self.blinker = next(item for item in self.baseline["entries"] if item["term"] == "blinker")

    def tearDown(self):
        self.temporary.cleanup()

    def add(self, value=None, name="new.json"):
        write(self.root / "batches" / name, batch() if value is None else value)

    def correct(self, changes, correction_id="fix-first", date="2026-10-11", name="first.json"):
        write(self.root / "corrections" / name, {"schemaVersion": 1, "correctionId": correction_id,
                                               "publishedOn": date, "changes": changes})

    def test_migration_preserves_every_baseline_field(self):
        result = compile_sources(self.root)
        self.assertEqual(self.baseline, result.catalog)
        self.assertEqual(len(self.baseline["entries"]), len(result.active))

    def test_index_and_lookup_only_include_primary_terms(self):
        result = compile_sources(self.root)
        self.assertIn("blinker", result.terms_text().splitlines())
        self.assertNotIn("turn signal", result.terms_text().splitlines())
        self.assertEqual([], result.lookup("turn signal"))
        self.assertEqual(self.blinker["id"], result.lookup(" BLINKER ")[0]["id"])

    def test_synonym_alias_can_be_added_as_independent_word(self):
        self.add(batch([entry("turn-signal", "turn signal")]))
        result = compile_sources(self.root)
        self.assertEqual(len(self.baseline["entries"]) + 1, len(result.active))
        self.assertEqual(self.blinker, result.records[self.blinker["id"]])
        self.assertNotEqual(self.blinker["id"], result.lookup("turn signal")[0]["id"])
        added = result.records["turn-signal"]
        self.assertEqual("turn signal", added["forms"][0]["speakText"])
        self.assertEqual("turn signal", added["listeningPrompt"])
        self.assertIsNone(added["forms"][0]["ipa"])

    def test_duplicate_id_is_rejected(self):
        self.add(batch([entry(self.blinker["id"], "different term")]))
        with self.assertRaisesRegex(ValueError, "id 重复"):
            compile_sources(self.root)

    def test_normalized_primary_duplicate_is_rejected(self):
        self.add(batch([entry("another-blinker", "  BLINKER  ")]))
        with self.assertRaisesRegex(ValueError, "主词重复"):
            compile_sources(self.root)

    def test_normalization_does_not_merge_synonyms_plurals_or_meaningful_hyphens(self):
        self.assertEqual(normalized_term("Ｒａｉｎ  Date"), normalized_term("rain date"))
        self.assertEqual(normalized_term("driver’s license"), normalized_term("driver's license"))
        self.assertEqual(normalized_term("check‑in"), normalized_term("check-in"))
        self.assertNotEqual(normalized_term("blinker"), normalized_term("turn signal"))
        self.assertNotEqual(normalized_term("signal"), normalized_term("signals"))
        self.assertNotEqual(normalized_term("check-in"), normalized_term("check in"))

    def test_missing_required_fields_and_optional_fields_are_rejected(self):
        for field in ENTRY_FIELDS:
            with self.subTest(missing=field):
                value = entry(); del value[field]
                self.add(batch([value]))
                with self.assertRaisesRegex(ValueError, "required property"):
                    compile_sources(self.root)
        for field in ("forms", "speakText", "listeningPrompt", "distinctSenseOf", "homophoneGroup", "confusableEntryIds"):
            with self.subTest(unwanted=field):
                value = entry(); value[field] = []
                self.add(batch([value]))
                with self.assertRaisesRegex(ValueError, "Additional properties"):
                    compile_sources(self.root)

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        self.add()
        path = self.root / "batches/new.json"
        path.write_text(path.read_text().replace('"schemaVersion": 1,', '"schemaVersion": 1, "schemaVersion": 1,'))
        with self.assertRaisesRegex(ValueError, "JSON 字段重复"):
            compile_sources(self.root)

    def test_duplicate_batch_id_and_cross_batch_terms_fail(self):
        self.add()
        self.add(batch([entry("another-id", "another term")]), "second.json")
        with self.assertRaisesRegex(ValueError, "batchId"):
            compile_sources(self.root)
        self.add(batch([entry("another-id", "RAIN DATE")], "life-second"), "second.json")
        with self.assertRaisesRegex(ValueError, "主词重复"):
            compile_sources(self.root)

    def test_invalid_dates_and_empty_examples_report_source_file(self):
        value = batch(date="2026-02-30"); self.add(value)
        with self.assertRaisesRegex(ValueError, "batches/new.json"):
            compile_sources(self.root)
        value = batch(); value["entries"][0]["examples"] = []; self.add(value)
        with self.assertRaisesRegex(ValueError, "examples"):
            compile_sources(self.root)

    def test_correction_preserves_id_added_date_and_existing_pronunciation(self):
        replacement = {name: deepcopy(self.blinker[name]) for name in ENTRY_FIELDS}
        replacement["explanationZh"] = "改进后的生活解释。"
        self.correct([{"action": "update", "id": self.blinker["id"], "expectedRevision": 1, "entry": replacement}])
        value = compile_sources(self.root).records[self.blinker["id"]]
        self.assertEqual(2, value["revision"])
        self.assertEqual(self.blinker["addedOn"], value["addedOn"])
        self.assertEqual("2026-10-11", value["updatedOn"])
        self.assertEqual(self.blinker["forms"], value["forms"])

    def test_stale_revision_and_unknown_correction_id_fail(self):
        self.correct([{"action": "archive", "id": self.blinker["id"], "expectedRevision": 2}])
        with self.assertRaisesRegex(ValueError, "修订版本已过期"):
            compile_sources(self.root)
        self.correct([{"action": "archive", "id": "unknown-word", "expectedRevision": 1}])
        with self.assertRaisesRegex(ValueError, "词条不存在"):
            compile_sources(self.root)

    def test_archive_and_restore_keep_id_and_reserved_primary_term(self):
        entry_id = self.blinker["id"]
        self.correct([{"action": "archive", "id": entry_id, "expectedRevision": 1}])
        archived = compile_sources(self.root)
        self.assertNotIn(entry_id, archived.active)
        self.assertIn("blinker", archived.terms_text().splitlines())
        self.assertEqual("archived", archived.lookup("blinker")[0]["status"])
        self.assertTrue(all(entry_id not in lesson["entryIds"] for lesson in archived.catalog["lessons"]))
        self.correct([{"action": "restore", "id": entry_id, "expectedRevision": 2}], "fix-restore", "2026-10-12", "restore.json")
        restored = compile_sources(self.root)
        self.assertIn(entry_id, restored.active)
        self.assertEqual(3, restored.records[entry_id]["revision"])
        self.assertEqual(self.blinker["addedOn"], restored.records[entry_id]["addedOn"])

    def test_archiving_does_not_allow_readding_the_same_primary(self):
        self.correct([{"action": "archive", "id": self.blinker["id"], "expectedRevision": 1}])
        self.add(batch([entry("new-blinker", "blinker")]))
        with self.assertRaisesRegex(ValueError, "主词重复"):
            compile_sources(self.root)

    def test_no_content_change_retains_original_version_and_hash(self):
        old = load_json(self.root / "manifest.json")
        report = prepare_incremental_release(self.root, self.output)
        self.assertFalse(report["changed"])
        self.assertEqual(old, load_json(self.output / "manifest.json"))

    def test_release_versions_hashes_and_retries_are_deterministic(self):
        self.add()
        report = prepare_incremental_release(self.root, self.output)
        self.assertTrue(report["changed"])
        self.assertEqual(4, report["contentVersion"])
        self.assertEqual(["rain-date"], report["added"])
        first = load_json(self.output / "manifest.json")
        again = prepare_incremental_release(self.root, self.output)
        self.assertEqual(report, again)
        self.assertEqual(first, load_json(self.output / "manifest.json"))
        payload = (self.output / first["catalog"]["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), first["catalog"]["sha256"])
        self.assertEqual(len(payload), first["catalog"]["byteLength"])

    def test_published_asset_corruption_is_rejected(self):
        manifest = load_json(self.root / "manifest.json")
        path = self.root / manifest["catalog"]["path"]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            prepare_incremental_release(self.root, self.output)

    def test_source_directory_cannot_be_used_as_output(self):
        with self.assertRaisesRegex(ValueError, "独立输出目录"):
            prepare_incremental_release(self.root, self.root)


class MemoryReleases:
    releases = {}
    publishes = 0
    fail = False

    def __init__(self, repository, cwd, run):
        self.cwd = cwd

    def get(self, tag):
        return self.releases.get(tag)

    def matches(self, release, output, manifest):
        return release["manifest"] == manifest and release["terms"] == (output / "terms.txt").read_text()

    def publish(self, tag, existing, output, manifest, body, commit):
        if existing:
            if not self.matches(existing, output, manifest):
                raise ValueError("已发布内容不同")
            return
        if self.fail:
            raise CommandError("injected upload failure")
        self.releases[tag] = {"tag_name": tag, "draft": False, "manifest": deepcopy(manifest),
                              "terms": (output / "terms.txt").read_text()}
        type(self).publishes += 1


class ReleaseTransportTests(unittest.TestCase):
    def test_interrupted_draft_is_found_even_when_tag_endpoint_returns_404(self):
        draft = {"id": 42, "tag_name": "vocab-v4", "draft": True, "assets": []}
        def run(arguments, cwd, input_text=None):
            if "/releases/tags/" in arguments[2]:
                raise CommandError("gh: Not Found (HTTP 404)")
            self.assertEqual(["--paginate", "--slurp"], arguments[-2:])
            return json.dumps([[{"tag_name": "app-v0.4.1"}], [draft]])
        self.assertEqual(draft, Releases("test/repo", Path.cwd(), run).get("vocab-v4"))

    def test_permissions_failure_is_not_mistaken_for_missing_release(self):
        def run(arguments, cwd, input_text=None):
            raise CommandError("HTTP 403")
        with self.assertRaisesRegex(CommandError, "403"):
            Releases("test/repo", Path.cwd(), run).get("vocab-v4")

    def test_upload_verification_fetches_by_release_id_before_publishing(self):
        calls = []
        draft = {"id": 42, "tag_name": "vocab-v4", "draft": True, "assets": []}
        def run(arguments, cwd, input_text=None):
            calls.append((arguments, input_text))
            if arguments[:3] == ["gh", "release", "upload"]:
                return ""
            if input_text is not None:
                value = json.loads(input_text)
                if not value["draft"]:
                    self.assertEqual("false", value["make_latest"])
                return json.dumps(draft)
            self.assertEqual("repos/test/repo/releases/42", arguments[2])
            return json.dumps(draft)
        class VerifiedReleases(Releases):
            def matches(self, release, output, manifest):
                self.assert_release = release
                return release["id"] == 42
        releases = VerifiedReleases("test/repo", Path.cwd(), run)
        releases.publish("vocab-v4", None, Path("/tmp/test-publication"),
                         {"contentVersion": 4, "catalog": {"path": "releases/v4-aaaaaaaaaaaa.json"}}, "notes", "a" * 40)
        self.assertEqual(42, releases.assert_release["id"])
        self.assertTrue(any(args == ["gh", "api", "repos/test/repo/releases/42"] for args, _ in calls))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="force-publish-test-")
        self.directory = Path(self.temporary.name)
        self.root, self.remote = self.directory / "source", self.directory / "remote.git"
        self.baseline = initialize(self.root)
        write(self.root / "batches/new.json", batch())
        command(["git", "init", "--bare", str(self.remote)], self.directory)
        command(["git", "init", "-b", "main"], self.root)
        command(["git", "config", "user.name", "Vocabulary test"], self.root)
        command(["git", "config", "user.email", "vocab-test@example.invalid"], self.root)
        command(["git", "add", "."], self.root)
        command(["git", "commit", "-m", "Seed incremental source"], self.root)
        command(["git", "remote", "add", "origin", str(self.remote)], self.root)
        command(["git", "push", "-u", "origin", "main"], self.root)
        (self.root / "uncommitted-notes.txt").write_text("Keep my local edits")
        MemoryReleases.releases = {}; MemoryReleases.publishes = 0; MemoryReleases.fail = False

    def tearDown(self):
        self.temporary.cleanup()

    def manifest(self):
        return json.loads(command(["git", "show", "main:manifest.json"], self.remote))

    def test_atomic_publication_and_repeat_run(self):
        report = publish_repository(self.root, "test/repo", release_factory=MemoryReleases)
        self.assertEqual(4, report["contentVersion"])
        self.assertEqual(4, self.manifest()["contentVersion"])
        self.assertEqual(1, MemoryReleases.publishes)
        second = publish_repository(self.root, "test/repo", release_factory=MemoryReleases)
        self.assertFalse(second["changed"])
        self.assertEqual(1, MemoryReleases.publishes)
        self.assertEqual("Keep my local edits", (self.root / "uncommitted-notes.txt").read_text())
        self.assertEqual(1, len(command(["git", "worktree", "list", "--porcelain"], self.root).split("worktree ")) - 1)

    def test_upload_failure_keeps_old_remote_manifest(self):
        MemoryReleases.fail = True
        with self.assertRaisesRegex(CommandError, "upload failure"):
            publish_repository(self.root, "test/repo", release_factory=MemoryReleases)
        self.assertEqual(3, self.manifest()["contentVersion"])

    def test_retry_after_push_failure_reuses_existing_release(self):
        rejected = False
        def run(arguments, cwd, input_text=None):
            nonlocal rejected
            if arguments[:3] == ["git", "push", "origin"] and not rejected:
                rejected = True
                raise CommandError("[rejected] main (fetch first)")
            return command(arguments, cwd, input_text)
        report = publish_repository(self.root, "test/repo", run, MemoryReleases)
        self.assertEqual(4, report["contentVersion"])
        self.assertEqual(1, MemoryReleases.publishes)

    def test_racing_source_commit_uses_new_version_without_losing_any_additions(self):
        raced = False
        def run(arguments, cwd, input_text=None):
            nonlocal raced
            if arguments[:3] == ["git", "push", "origin"] and not raced:
                raced = True
                newcomer = self.directory / "newcomer"
                command(["git", "clone", "--branch", "main", str(self.remote), str(newcomer)], self.directory)
                write(newcomer / "batches/second.json", batch([entry("shelf-stable", "shelf-stable")], "life-second", "2026-10-11"))
                command(["git", "add", "."], newcomer)
                command(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "Another addition"], newcomer)
                command(["git", "push", "origin", "main"], newcomer)
            return command(arguments, cwd, input_text)
        report = publish_repository(self.root, "test/repo", run, MemoryReleases)
        self.assertEqual(5, report["contentVersion"])
        self.assertEqual(2, MemoryReleases.publishes)
        self.assertIn("vocab-v4", MemoryReleases.releases)
        current = self.manifest()
        catalog = json.loads(command(["git", "show", "main:" + current["catalog"]["path"]], self.remote))
        self.assertTrue({"rain-date", "shelf-stable"} <= {item["id"] for item in catalog["entries"]})


if __name__ == "__main__":
    unittest.main()
