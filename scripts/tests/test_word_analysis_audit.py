from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_word_analysis import validate_reviews, fingerprint, cached_review, save_review, write_corrections
from incremental_vocabulary import compile_sources
from test_incremental_vocabulary import initialize, write


def review(entry, text="", kind="none", cue=""):
    return {"id": entry["id"], "textZh": text, "kind": kind,
            "reasonZh": "现有用法已充分解释，无需补充。", "cueZh": cue}


class WordAnalysisAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'repo'
        baseline = initialize(self.root)
        write(self.root / 'corrections/concise.json', {
            'schemaVersion': 3, 'correctionId': 'word-analysis-base', 'publishedOn': '2026-11-23',
            'changes': [{'action': 'analyze', 'id': e['id'], 'expectedRevision': e['revision'],
                         'wordAnalysis': {'textZh': ''}} for e in baseline['entries']]})
        c = compile_sources(self.root)
        self.entries = [e for e in c.records.values() if e['id'] in c.active]
        self.cache = Path(self.temp.name) / 'cache'; self.cache.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_all_entries_including_empty_notes_require_explicit_decisions(self):
        valid = [review(e) for e in self.entries]
        self.assertEqual(len(self.entries), len(validate_reviews({'reviews': valid}, self.entries)))
        for items in (valid[:-1], valid + valid[:1], [{**valid[0], 'id': 'unknown'}] + valid[1:]):
            with self.assertRaises(ValueError):
                validate_reviews({'reviews': items}, self.entries)

    def test_mnemonic_requires_a_traceable_english_cue_and_consistent_kind(self):
        entry = self.entries[0]
        invalid = [review(entry, '有内容却称省略。'), review(entry, '', 'formation'),
                   review(entry, '把袜子放进篮子。', 'mnemonic'),
                   review(entry, '把袜子放进篮子。', 'mnemonic', '只描述使用场景'),
                   review(entry, 'blink 表示闪烁。', 'formation', 'blink')]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_reviews({'reviews': [item]}, [entry])
        good = review(entry, '可想成远处的靶子：long 很远，shot 这一枪就难打中。',
                      'mnemonic', 'long 对应远距离；shot 对应射击；难打中连接希望渺茫。')
        validate_reviews({'reviews': [good]}, [entry])

    def test_cache_invalidates_on_revision_content_or_deployment_changes(self):
        entry = self.entries[0]
        save_review(self.cache, entry, 'model', review(entry))
        self.assertIsNotNone(cached_review(self.cache, entry, 'model'))
        for field, value in [('revision', entry['revision'] + 1), ('usageNotesZh', ['新用法']),
                             ('wordAnalysis', {'textZh': '已有新解释。'})]:
            changed = deepcopy(entry); changed[field] = value
            self.assertIsNone(cached_review(self.cache, changed, 'model'))
        self.assertNotEqual(fingerprint(entry, 'model'), fingerprint(entry, 'another-model'))

    def test_partial_audits_and_output_collisions_write_nothing(self):
        save_review(self.cache, self.entries[0], 'model', review(self.entries[0]))
        before = sorted((self.root / 'corrections').glob('*.json'))
        with self.assertRaisesRegex(ValueError, '缺少'):
            write_corrections(self.root, self.entries, self.cache, 'model', '2026-11-24')
        self.assertEqual(before, sorted((self.root / 'corrections').glob('*.json')))
        for e in self.entries: save_review(self.cache, e, 'model', review(e, 'blink 表示闪烁。', 'formation'))
        write(self.root / 'reviews/2026-11-24-mnemonic-audit.json', {'existing': True})
        with self.assertRaisesRegex(ValueError, '不覆盖'):
            write_corrections(self.root, self.entries, self.cache, 'model', '2026-11-24')
        self.assertEqual(before, sorted((self.root / 'corrections').glob('*.json')))

    def test_report_covers_all_but_only_changed_words_receive_a_revision(self):
        for e in self.entries: save_review(self.cache, e, 'model', review(e))
        first = self.entries[0]
        save_review(self.cache, first, 'model', review(first, 'blink 表示闪烁。', 'formation'))
        result = write_corrections(self.root, self.entries, self.cache, 'model', '2026-11-24')
        self.assertEqual(len(self.entries), result['entryCount'])
        self.assertEqual(1, result['changedCount'])
        self.assertEqual({'keep', 'add'}, {e['action'] for e in result['entries']})
        actual = compile_sources(self.root)
        for entry in self.entries:
            updated = actual.records[entry['id']]
            self.assertEqual(entry['revision'] + (entry['id'] == first['id']), updated['revision'])
            for field in entry:
                if field not in ('revision', 'updatedOn', 'wordAnalysis'):
                    self.assertEqual(entry[field], updated[field])
        report = json.loads((self.root / 'reviews/2026-11-24-mnemonic-audit.json').read_text())
        self.assertEqual(result, report)


if __name__ == '__main__':
    unittest.main()
