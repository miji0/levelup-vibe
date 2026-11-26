CREATE TABLE sources (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner_settings(id),
    name text NOT NULL, input_url text NOT NULL, collection_url text NOT NULL,
    collection_url_hash text NOT NULL,
    collector_type text NOT NULL CHECK (collector_type IN ('rss', 'atom', 'html')),
    adapter_key text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'deleted')),
    generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
    initialization_state text NOT NULL DEFAULT 'pending'
        CHECK (initialization_state IN ('pending', 'running', 'ready', 'failed')),
    etag text, last_modified text, last_attempt_at timestamptz, last_success_at timestamptz,
    last_usable_at timestamptz, last_result text CHECK (last_result IN ('success', 'partial', 'failed')),
    last_error_code text, last_error_message text, deleted_at timestamptz,
    created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    UNIQUE (owner_id, collection_url_hash), UNIQUE (id, owner_id),
    CHECK ((status = 'deleted') = (deleted_at IS NOT NULL)),
    CHECK (collector_type <> 'html' OR adapter_key IS NOT NULL)
);
CREATE TABLE subscription_epochs (
    id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES sources(id),
    generation bigint NOT NULL CHECK (generation > 0), started_at timestamptz NOT NULL,
    ended_at timestamptz, baseline_completed_at timestamptz,
    reason text NOT NULL CHECK (reason IN ('first_add', 'resume', 'readd')),
    UNIQUE (source_id, generation), UNIQUE (id, source_id),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX subscription_epochs_active ON subscription_epochs(source_id)
    WHERE ended_at IS NULL;
CREATE TABLE articles (
    id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES sources(id),
    first_epoch_id uuid NOT NULL, title text NOT NULL, canonical_url text NOT NULL,
    intro text, tags text[] NOT NULL DEFAULT '{}', published_at timestamptz,
    publication_precision text NOT NULL
        CHECK (publication_precision IN ('timestamp', 'date', 'missing', 'invalid')),
    publication_raw text, first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL,
    metadata_updated_at timestamptz NOT NULL, eligible_on date,
    notification_state text NOT NULL
        CHECK (notification_state IN ('baseline', 'pending', 'suppressed', 'notified')),
    suppression_reason text CHECK (suppression_reason IN
        ('initial_import', 'inactive_period', 'source_disabled', 'source_deleted')),
    notified_digest_id uuid,
    FOREIGN KEY (first_epoch_id, source_id) REFERENCES subscription_epochs(id, source_id),
    UNIQUE (id, source_id),
    CHECK ((publication_precision IN ('timestamp', 'date')) = (published_at IS NOT NULL)),
    CHECK (notification_state <> 'pending' OR eligible_on IS NOT NULL),
    CHECK (notification_state NOT IN ('baseline', 'suppressed') OR eligible_on IS NULL)
);
CREATE INDEX articles_source ON articles(source_id);
CREATE INDEX articles_eligible ON articles(eligible_on) WHERE notification_state = 'pending';
CREATE TABLE article_keys (
    source_id uuid NOT NULL, key_type text NOT NULL CHECK (key_type IN ('guid', 'url')),
    key_hash text NOT NULL, article_id uuid NOT NULL, key_value text NOT NULL,
    created_at timestamptz NOT NULL, PRIMARY KEY (source_id, key_type, key_hash),
    FOREIGN KEY (article_id, source_id) REFERENCES articles(id, source_id)
);
CREATE TABLE article_states (
    article_id uuid PRIMARY KEY REFERENCES articles(id),
    is_read boolean NOT NULL DEFAULT false, is_saved boolean NOT NULL DEFAULT false,
    is_hidden boolean NOT NULL DEFAULT false,
    read_at timestamptz, saved_at timestamptz, hidden_at timestamptz,
    created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    CHECK (is_read = (read_at IS NOT NULL)), CHECK (is_saved = (saved_at IS NOT NULL)),
    CHECK (is_hidden = (hidden_at IS NOT NULL))
);
-- Subscription changes must preserve submitted/unknown reservations even before mail is enabled.
CREATE TABLE digests (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner_settings(id),
    digest_date date NOT NULL,
    state text NOT NULL CHECK (state IN ('draft', 'empty', 'paused', 'ready', 'sending',
        'accepted', 'failed', 'unknown', 'cancelled', 'missed')),
    reason_code text, scheduled_at timestamptz NOT NULL, start_deadline_at timestamptz NOT NULL,
    started_at timestamptz, snapshot_at timestamptz, accepted_at timestamptz,
    created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    UNIQUE (owner_id, digest_date), UNIQUE (id, owner_id),
    CHECK (start_deadline_at > scheduled_at)
);
ALTER TABLE articles ADD CONSTRAINT articles_digest_fk
    FOREIGN KEY (notified_digest_id) REFERENCES digests(id);
CREATE TABLE digest_items (
    digest_id uuid NOT NULL REFERENCES digests(id), article_id uuid NOT NULL REFERENCES articles(id),
    title_snapshot text NOT NULL, url_snapshot text NOT NULL, source_name_snapshot text NOT NULL,
    sort_position integer NOT NULL CHECK (sort_position > 0), shown_in_email boolean NOT NULL,
    exclusion_reason text,
    reservation_state text NOT NULL CHECK (reservation_state IN ('none', 'held', 'released', 'consumed')),
    created_at timestamptz NOT NULL, PRIMARY KEY (digest_id, article_id),
    UNIQUE (digest_id, sort_position)
);
CREATE UNIQUE INDEX digest_items_reserved ON digest_items(article_id)
    WHERE reservation_state IN ('held', 'consumed');
ALTER TABLE gmail_connections ADD CONSTRAINT gmail_connections_owner_unique UNIQUE (id, owner_id);
CREATE TABLE deliveries (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner_settings(id),
    kind text NOT NULL CHECK (kind IN ('digest', 'test')), digest_id uuid,
    gmail_connection_id uuid NOT NULL, connection_version bigint NOT NULL,
    revision integer NOT NULL CHECK (revision > 0), request_key text NOT NULL UNIQUE,
    mime_message_id text NOT NULL UNIQUE, from_address text NOT NULL, to_address text NOT NULL,
    subject text NOT NULL, mime_payload bytea NOT NULL, payload_sha256 text NOT NULL,
    state text NOT NULL CHECK (state IN ('prepared', 'sending', 'accepted', 'failed',
        'unknown', 'cancelled')), provider_message_id text UNIQUE,
    prepared_at timestamptz NOT NULL, submitted_at timestamptz, accepted_at timestamptz,
    last_error_code text, finished_at timestamptz, http_status integer,
    verification_outcome text CHECK (verification_outcome IN
        ('confirmed_accepted', 'confirmed_not_accepted', 'unresolved')),
    verification_note text, verified_at timestamptz,
    FOREIGN KEY (digest_id, owner_id) REFERENCES digests(id, owner_id),
    FOREIGN KEY (gmail_connection_id, owner_id) REFERENCES gmail_connections(id, owner_id),
    UNIQUE (digest_id, revision), CHECK (from_address = to_address),
    CHECK ((kind = 'digest') = (digest_id IS NOT NULL))
);
CREATE UNIQUE INDEX deliveries_submitted ON deliveries(digest_id)
    WHERE submitted_at IS NOT NULL AND kind = 'digest';
CREATE UNIQUE INDEX deliveries_accepted ON deliveries(digest_id)
    WHERE state = 'accepted' AND kind = 'digest';
CREATE TABLE job_runs (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner_settings(id),
    kind text NOT NULL CHECK (kind IN ('collect', 'collect_final', 'baseline', 'digest', 'test_email')),
    source_id uuid, source_generation bigint, dedup_key text NOT NULL UNIQUE,
    input jsonb NOT NULL DEFAULT '{}',
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'skipped')),
    available_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz,
    lease_token uuid, lease_expires_at timestamptz, heartbeat_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    result_code text, result_summary jsonb,
    FOREIGN KEY (source_id, owner_id) REFERENCES sources(id, owner_id),
    CHECK ((kind IN ('collect', 'collect_final', 'baseline')) =
        (source_id IS NOT NULL AND source_generation IS NOT NULL)),
    CHECK (state <> 'running' OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL))
);
CREATE INDEX job_runs_ready ON job_runs(owner_id, available_at, id) WHERE state = 'queued';
CREATE TABLE collection_entry_issues (
    id uuid PRIMARY KEY, source_id uuid NOT NULL, epoch_id uuid NOT NULL,
    entry_fingerprint text NOT NULL, identity_hashes text[] NOT NULL DEFAULT '{}',
    first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL,
    observed_as_baseline boolean NOT NULL, error_code text NOT NULL,
    state text NOT NULL CHECK (state IN ('open', 'resolved')),
    resolved_article_id uuid, resolved_at timestamptz, last_job_id uuid NOT NULL REFERENCES job_runs(id),
    FOREIGN KEY (epoch_id, source_id) REFERENCES subscription_epochs(id, source_id),
    FOREIGN KEY (resolved_article_id, source_id) REFERENCES articles(id, source_id),
    UNIQUE (source_id, epoch_id, entry_fingerprint),
    CHECK ((state = 'resolved') = (resolved_article_id IS NOT NULL AND resolved_at IS NOT NULL))
);
CREATE INDEX collection_entry_issues_open ON collection_entry_issues(source_id, epoch_id)
    WHERE state = 'open';
