from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_vocabulary as wire
from incremental_vocabulary import compile_sources, prepare_incremental_release
from enrich_word_analysis import validate_response, save_result, cached_result, write_corrections, request_json, NoRedirect
from word_analysis import wire_entry, render_analysis
from test_incremental_vocabulary import initialize, write, batch, entry


ANALYSIS = {"baseFormZh": "blinker 是名词原形。", "rootsZh": "blink 表示闪烁。",
            "affixesZh": "-er 在这里构成表示事物的名词。", "mnemonicZh": "想象转弯前一闪一闪的灯。"}


class WordAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.baseline = initialize(self.root)
        self.first = self.baseline["entries"][0]

    def tearDown(self):
        self.temp.cleanup()

    def correction(self, analysis=ANALYSIS, revision=1):
        write(self.root / "corrections/analysis.json", {
            "schemaVersion": 2, "correctionId": "fix-analysis", "publishedOn": "2026-11-23",
            "changes": [{"action": "analyze", "id": self.first["id"], "expectedRevision": revision,
                         "wordAnalysis": deepcopy(analysis)}]})

    def test_analysis_correction_preserves_original_data_and_legacy_protocol(self):
        self.correction()
        result = compile_sources(self.root)
        source = result.records[self.first["id"]]
        self.assertEqual(ANALYSIS, source["wordAnalysis"])
        self.assertEqual(self.first["usageNotesZh"], source["usageNotesZh"])
        published = next(e for e in result.catalog["entries"] if e["id"] == self.first["id"])
        self.assertEqual(set(self.first), set(published))
        for field in self.first:
            if field not in ("revision", "updatedOn", "usageNotesZh"):
                self.assertEqual(self.first[field], published[field], field)
        self.assertEqual(2, published["revision"])
        self.assertEqual(render_analysis(ANALYSIS), published["usageNotesZh"][-1])
        self.assertEqual(result.catalog, compile_sources(self.root).catalog)
        self.assertEqual(ANALYSIS, result.lookup(self.first["term"])[0]["wordAnalysis"])
        report = prepare_incremental_release(self.root, Path(self.temp.name) / "out")
        self.assertEqual([self.first["id"]], report["updated"])

    def test_stale_analysis_cannot_overwrite_newer_revision(self):
        self.correction(revision=2)
        with self.assertRaisesRegex(ValueError, "修订版本已过期"):
            compile_sources(self.root)

    def test_v2_batches_and_updates_require_all_four_analysis_fields(self):
        value = batch(); value["schemaVersion"] = 2
        with self.assertRaises(Exception):
            wire.validate_schema(value, "batch.schema.json")
        value["entries"][0]["wordAnalysis"] = deepcopy(ANALYSIS)
        wire.validate_schema(value, "batch.schema.json")
        for field in ANALYSIS:
            invalid = deepcopy(value)
            invalid["entries"][0]["wordAnalysis"].pop(field)
            with self.subTest(field=field), self.assertRaises(Exception):
                wire.validate_schema(invalid, "batch.schema.json")
        correction = {"schemaVersion": 2, "correctionId": "fix-test", "publishedOn": "2026-11-23",
                      "changes": [{"action": "update", "id": "rain-date", "expectedRevision": 1, "entry": entry()}]}
        with self.assertRaises(Exception):
            wire.validate_schema(correction, "correction.schema.json")

    def test_policy_prevents_new_words_without_analysis_even_in_legacy_batches(self):
        changes = [{"action": "analyze", "id": e["id"], "expectedRevision": 1, "wordAnalysis": ANALYSIS}
                   for e in self.baseline["entries"]]
        write(self.root / "corrections/all.json", {"schemaVersion": 2, "correctionId": "fix-all",
                                                   "publishedOn": "2026-11-23", "changes": changes})
        write(self.root / "vocabulary/analysis-policy.json", {"schemaVersion": 1, "requireWordAnalysis": True})
        compile_sources(self.root)
        write(self.root / "batches/new.json", batch())
        with self.assertRaisesRegex(ValueError, "rain-date"):
            compile_sources(self.root)

    def test_content_edits_cannot_silently_reuse_stale_analysis(self):
        self.correction()
        replacement = {k: deepcopy(self.first[k]) for k in entry()}
        write(self.root / "corrections/later.json", {"schemaVersion": 1, "correctionId": "fix-later",
              "publishedOn": "2026-11-24", "changes": [{"action": "update", "id": self.first["id"],
              "expectedRevision": 2, "entry": replacement}]})
        with self.assertRaisesRegex(ValueError, "过期解析"):
            compile_sources(self.root)

    def test_ten_existing_notes_are_preserved_and_length_limit_is_enforced(self):
        item = deepcopy(self.first)
        item["usageNotesZh"] = [f"原有说明 {i}" for i in range(10)]
        item["wordAnalysis"] = ANALYSIS
        result = wire_entry(item)
        self.assertEqual(10, len(result["usageNotesZh"]))
        self.assertEqual(item["usageNotesZh"][:9], result["usageNotesZh"][:9])
        self.assertTrue(result["usageNotesZh"][-1].startswith(item["usageNotesZh"][-1] + "\n\n"))
        item["usageNotesZh"][-1] = "长" * 3000
        with self.assertRaisesRegex(ValueError, "3000"):
            wire_entry(item)

    def test_generation_rejects_missing_duplicate_unknown_and_invalid_outputs(self):
        valid = {"id": self.first["id"], "wordAnalysis": ANALYSIS}
        for values in ([], [valid, valid], [{**valid, "id": "unknown"}],
                       [{**valid, "wordAnalysis": {**ANALYSIS, "rootsZh": " "}}],
                       [{**valid, "wordAnalysis": {**ANALYSIS, "rootsZh": "字" * 401}}]):
            with self.subTest(values=values), self.assertRaises(Exception):
                validate_response({"entries": values}, [self.first])

    def test_cache_changes_with_context_and_corrections_need_full_coverage(self):
        cache = Path(self.temp.name) / "cache"; cache.mkdir()
        save_result(cache, self.first, "deployment", ANALYSIS)
        self.assertEqual(ANALYSIS, cached_result(cache, self.first, "deployment"))
        changed = deepcopy(self.first); changed["definitionZh"] = "different meaning"
        self.assertIsNone(cached_result(cache, changed, "deployment"))
        self.assertIsNone(cached_result(cache, self.first, "another-deployment"))
        with self.assertRaisesRegex(ValueError, "缺少缓存"):
            write_corrections(self.root, self.baseline["entries"], cache, "deployment", "2026-11-23")
        self.assertFalse((self.root / "corrections").exists())

    def test_transport_never_echoes_error_body_or_follows_redirects(self):
        secret = "test-secret-not-a-real-key"
        error = HTTPError("https://example.test", 401, "Unauthorized", {},
                          io.BytesIO(json.dumps({"error": {"code": secret, "message": secret}}).encode()))
        with patch("enrich_word_analysis.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(RuntimeError) as raised:
                request_json({}, "https://example.test/openai/v1", secret)
            self.assertNotIn(secret, str(raised.exception))
            self.assertIn("401", str(raised.exception))
            self.assertEqual(1, opener.return_value.open.call_count)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, None, "https://another.test"))

    def test_truncated_model_output_is_not_treated_as_complete(self):
        body = {"choices": [{"finish_reason": "length", "message": {"content": '{"entries":[]}'}}]}
        with patch("enrich_word_analysis.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
            with self.assertRaisesRegex(ValueError, "未完整返回"):
                request_json({}, "https://example.test/openai/v1", "test-key")

    def test_later_output_collision_cannot_leave_partial_corrections(self):
        cache = Path(self.temp.name) / "cache"; cache.mkdir()
        entries = []
        for i in range(101):
            item = {**self.first, "id": f"test-{i}"}
            entries.append(item)
            save_result(cache, item, "deployment", ANALYSIS)
        existing = self.root / "corrections/2026-11-23-word-analysis-002.json"
        write(existing, {"existing": True})
        with self.assertRaisesRegex(ValueError, "不覆盖"):
            write_corrections(self.root, entries, cache, "deployment", "2026-11-23")
        self.assertEqual([existing], list((self.root / "corrections").iterdir()))


if __name__ == "__main__":
    unittest.main()
