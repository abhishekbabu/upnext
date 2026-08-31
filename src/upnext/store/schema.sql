-- upnext's local library.
--
-- One `titles` table covers shows and films from the start, keyed by `kind`,
-- so adding films later is data rather than a migration. A watch of a film is
-- a row with a null episode_id; a watch of a show is a row that points at one
-- episode.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS titles (
    id             INTEGER PRIMARY KEY,
    kind           TEXT    NOT NULL CHECK (kind IN ('show', 'movie')),
    name           TEXT    NOT NULL,
    year           INTEGER,

    -- Source-of-truth identifiers. tvdb_id is what a TV Time export carries;
    -- tmdb_id is what enrichment resolves it to and everything else hangs off.
    tmdb_id        INTEGER,
    tvdb_id        INTEGER,
    imdb_id        TEXT,

    overview       TEXT,
    poster_path    TEXT,
    backdrop_path  TEXT,
    -- The show's own status at the source ("Ended", "Returning Series"), not
    -- the user's. The user's lives in title_state.status.
    air_status     TEXT,
    first_air_date TEXT,
    last_air_date  TEXT,
    -- Total episodes the source says exist, for progress against the library.
    total_episodes INTEGER,
    runtime        INTEGER,

    enriched_at    TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS titles_tvdb ON titles (kind, tvdb_id) WHERE tvdb_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS titles_tmdb ON titles (kind, tmdb_id) WHERE tmdb_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS titles_name ON titles (name);

CREATE TABLE IF NOT EXISTS episodes (
    id             INTEGER PRIMARY KEY,
    title_id       INTEGER NOT NULL REFERENCES titles (id) ON DELETE CASCADE,
    season_number  INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,

    name           TEXT,
    overview       TEXT,
    air_date       TEXT,
    runtime        INTEGER,
    still_path     TEXT,

    tmdb_id        INTEGER,
    tvdb_id        INTEGER,

    UNIQUE (title_id, season_number, episode_number)
);

-- One row per viewing, not per episode: rewatches are separate rows, which is
-- what makes "watched Arrow twice" representable at all.
CREATE TABLE IF NOT EXISTS watches (
    id          INTEGER PRIMARY KEY,
    title_id    INTEGER NOT NULL REFERENCES titles (id) ON DELETE CASCADE,
    -- Null for a film, where the title is the thing watched.
    episode_id  INTEGER REFERENCES episodes (id) ON DELETE CASCADE,
    watched_at  TEXT    NOT NULL,
    is_rewatch  INTEGER NOT NULL DEFAULT 0,
    -- The exporting service's own id for the episode watched. TV Time issues
    -- one per viewing even for shows whose season/episode numbers it does not
    -- fill in, so this is what tells two such watches apart — and what makes
    -- re-importing an export converge instead of accumulating rows.
    source_episode_id TEXT,
    -- Where the row came from: 'tvtime' for imported history, 'upnext' for
    -- anything marked in the app. Import is idempotent per source.
    source      TEXT    NOT NULL DEFAULT 'upnext'
);

-- Two identities, one per shape of row, both partial because a table-level
-- UNIQUE cannot be conditional. With the source's episode id, that id and the
-- timestamp are the viewing; without one, the episode and the timestamp are.
-- Collapsing the two into a single constraint is what a first pass did, and it
-- rejected a legitimate row: TV Time can stamp two distinct episodes with the
-- same season/episode numbers and the same second.
CREATE UNIQUE INDEX IF NOT EXISTS watches_source_episode
    ON watches (title_id, source, source_episode_id, watched_at)
    WHERE source_episode_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS watches_episode_time
    ON watches (title_id, episode_id, watched_at, source)
    WHERE source_episode_id IS NULL AND episode_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS watches_title ON watches (title_id);
CREATE INDEX IF NOT EXISTS watches_at ON watches (watched_at);

-- The user's relationship to a title, as opposed to the title's own facts.
CREATE TABLE IF NOT EXISTS title_state (
    title_id            INTEGER PRIMARY KEY REFERENCES titles (id) ON DELETE CASCADE,
    status              TEXT    NOT NULL CHECK (status IN ('watching', 'completed', 'watchlist', 'stopped')),
    is_favorite         INTEGER NOT NULL DEFAULT 0,
    -- 1-10 in upnext's own scale; a TV Time 1-5 rating is doubled on import.
    rating              INTEGER,
    -- What the export claimed, kept because TV Time reports a seen count for
    -- shows whose per-episode rows it no longer has. Where the two disagree,
    -- the watches table is what the UI counts and this is the footnote.
    reported_watched    INTEGER,
    followed_at         TEXT,
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS title_state_status ON title_state (status);
