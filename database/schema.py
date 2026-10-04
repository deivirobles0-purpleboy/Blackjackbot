SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_config (
    guild_id BIGINT NOT NULL,
    language VARCHAR(2) NOT NULL CHECK (language IN ('ES', 'BR')),
    channel_id BIGINT,
    min_minutes INTEGER CHECK (min_minutes > 0),
    max_minutes INTEGER CHECK (max_minutes > 0),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    next_drop_at TIMESTAMPTZ,
    last_drop_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, language),
    CHECK ((min_minutes IS NULL AND max_minutes IS NULL)
           OR (min_minutes IS NOT NULL AND max_minutes IS NOT NULL AND max_minutes >= min_minutes)),
    CHECK (NOT enabled OR (channel_id IS NOT NULL AND min_minutes IS NOT NULL
                          AND max_minutes IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS user_candies (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    language VARCHAR(2) NOT NULL CHECK (language IN ('ES', 'BR')),
    candies BIGINT NOT NULL DEFAULT 0 CHECK (candies >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, user_id, language)
);
CREATE INDEX IF NOT EXISTS user_candies_ranking
    ON user_candies (guild_id, language, candies DESC, user_id);
CREATE TABLE IF NOT EXISTS admin_logs (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    admin_id BIGINT NOT NULL,
    target_user_id BIGINT,
    language VARCHAR(2) CHECK (language IN ('ES', 'BR')),
    action TEXT NOT NULL,
    amount BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS door_drops (
    id UUID PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    language VARCHAR(2) NOT NULL CHECK (language IN ('ES', 'BR')),
    channel_id BIGINT NOT NULL,
    message_id BIGINT UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('publishing', 'open', 'processing',
                                         'finished', 'cancelled', 'expired')),
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    rewards_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processing_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    FOREIGN KEY (guild_id, language) REFERENCES event_config (guild_id, language)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_automatic_door
    ON door_drops (guild_id, language)
    WHERE NOT is_test AND status IN ('publishing', 'open', 'processing');
CREATE INDEX IF NOT EXISTS live_door_status ON door_drops (status)
    WHERE status IN ('publishing', 'open', 'processing');
CREATE TABLE IF NOT EXISTS door_winners (
    drop_id UUID NOT NULL REFERENCES door_drops (id),
    user_id BIGINT NOT NULL,
    slot SMALLINT NOT NULL CHECK (slot BETWEEN 1 AND 2),
    candies SMALLINT NOT NULL CHECK (candies BETWEEN -5 AND 5),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (drop_id, user_id),
    UNIQUE (drop_id, slot)
);

-- Idempotent upgrade: preserve scores, settings and existing winning doors.
ALTER TABLE event_config ADD COLUMN IF NOT EXISTS win_percent SMALLINT NOT NULL
    DEFAULT 100 CHECK (win_percent BETWEEN 0 AND 100);
ALTER TABLE door_drops ADD COLUMN IF NOT EXISTS candy_win BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE door_winners DROP CONSTRAINT IF EXISTS door_winners_candies_check;
ALTER TABLE door_winners ADD CONSTRAINT door_winners_candies_check
    CHECK (candies BETWEEN -5 AND 5);
ALTER TABLE door_drops ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE door_drops ADD COLUMN IF NOT EXISTS delete_at TIMESTAMPTZ;
ALTER TABLE door_drops ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE door_drops DROP CONSTRAINT IF EXISTS door_drops_status_check;
ALTER TABLE door_drops ADD CONSTRAINT door_drops_status_check CHECK
    (status IN ('publishing','open','processing','finished','cancelled','expired'));
UPDATE door_drops SET expires_at=now()+interval '6 seconds'
    WHERE status='open' AND expires_at IS NULL
    AND NOT EXISTS (SELECT 1 FROM door_winners WHERE drop_id=door_drops.id);
CREATE INDEX IF NOT EXISTS pending_door_deletion ON door_drops (delete_at)
    WHERE delete_at IS NOT NULL AND deleted_at IS NULL;
"""
