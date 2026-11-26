-- Short-lived operational counters; not article, subscription or delivery history.
CREATE TABLE request_limits (
    owner_id uuid NOT NULL REFERENCES owner_settings(id), scope text NOT NULL,
    minute bigint NOT NULL, count integer NOT NULL CHECK (count > 0),
    PRIMARY KEY (owner_id,scope,minute)
);
