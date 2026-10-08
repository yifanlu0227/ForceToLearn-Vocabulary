-- Independent editorial vocabulary database; no messaging-service metadata.
-- SQLite-compatible schema. Learning progress belongs in the phone database.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    term TEXT NOT NULL CHECK (length(trim(term)) > 0),
    parts_of_speech_json TEXT NOT NULL CHECK (json_valid(parts_of_speech_json)),
    definition_zh TEXT NOT NULL,
    explanation_zh TEXT NOT NULL,
    usage_notes_zh_json TEXT NOT NULL CHECK (json_valid(usage_notes_zh_json)),
    tags_json TEXT NOT NULL CHECK (json_valid(tags_json)),
    listening_prompt TEXT NOT NULL,
    homophone_group TEXT,
    confusable_entry_ids_json TEXT NOT NULL CHECK (json_valid(confusable_entry_ids_json)),
    added_on TEXT NOT NULL,
    updated_on TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived'))
);

CREATE TABLE IF NOT EXISTS forms (
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    text TEXT NOT NULL,
    locale TEXT NOT NULL,
    respelling TEXT NOT NULL,
    ipa TEXT,
    speak_text TEXT NOT NULL,
    audio_path TEXT,
    audio_sha256 TEXT,
    PRIMARY KEY (entry_id, position),
    UNIQUE (entry_id, text),
    CHECK ((audio_path IS NULL) = (audio_sha256 IS NULL))
);

CREATE TABLE IF NOT EXISTS examples (
    entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    english TEXT NOT NULL,
    chinese TEXT NOT NULL,
    scenario_zh TEXT NOT NULL,
    PRIMARY KEY (entry_id, position)
);

CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    published_on TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lesson_entries (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    entry_id TEXT NOT NULL REFERENCES entries(id),
    position INTEGER NOT NULL CHECK (position >= 0),
    PRIMARY KEY (lesson_id, entry_id),
    UNIQUE (lesson_id, position)
);

-- Published snapshots are immutable. Roll back by publishing a new version.
CREATE TABLE IF NOT EXISTS releases (
    content_version INTEGER PRIMARY KEY CHECK (content_version >= 1),
    schema_version INTEGER NOT NULL,
    published_on TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    byte_length INTEGER NOT NULL,
    entry_count INTEGER NOT NULL,
    catalog_json TEXT NOT NULL CHECK (json_valid(catalog_json))
);

CREATE INDEX IF NOT EXISTS entries_status ON entries(status);
