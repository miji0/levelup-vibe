CREATE TABLE owner_settings (
    id uuid PRIMARY KEY,
    singleton boolean NOT NULL UNIQUE DEFAULT true CHECK (singleton = true),
    auth_provider text NOT NULL DEFAULT 'google' CHECK (auth_provider = 'google'),
    auth_subject text NOT NULL,
    auth_email text NOT NULL,
    notifications_enabled boolean NOT NULL DEFAULT false,
    timezone text NOT NULL DEFAULT 'Asia/Seoul' CHECK (timezone = 'Asia/Seoul'),
    created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    UNIQUE(auth_provider, auth_subject)
);
CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner_settings(id),
    token_hash text NOT NULL UNIQUE, csrf_token text NOT NULL,
    created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at = created_at + interval '604800 seconds')
);
CREATE INDEX auth_sessions_owner ON auth_sessions(owner_id);
CREATE TABLE oauth_states (
    state_hash text PRIMARY KEY, owner_id uuid NOT NULL REFERENCES owner_settings(id),
    purpose text NOT NULL CHECK (purpose IN ('site_login', 'gmail_connect')),
    session_binding_hash text NOT NULL, verifier_ciphertext bytea NOT NULL,
    nonce_hash text NOT NULL, created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL, consumed_at timestamptz
);
CREATE TABLE gmail_connections (
    id uuid PRIMARY KEY, owner_id uuid NOT NULL UNIQUE REFERENCES owner_settings(id),
    google_subject text NOT NULL, email text NOT NULL, scopes text[] NOT NULL,
    state text NOT NULL CHECK (state IN ('connected', 'reauth_required', 'disconnected')),
    refresh_token_ciphertext bytea, encryption_key_id text,
    connected_at timestamptz, last_refresh_at timestamptz, disconnected_at timestamptz,
    last_error_code text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    CHECK (state <> 'disconnected' OR refresh_token_ciphertext IS NULL)
);
