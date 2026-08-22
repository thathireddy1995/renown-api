CREATE TABLE IF NOT EXISTS web_analytics_events (
    id BIGSERIAL PRIMARY KEY,
    visitor_hash VARCHAR(64) NOT NULL,
    session_id VARCHAR(32) NOT NULL,
    event_name VARCHAR(40) NOT NULL,
    path VARCHAR(500) NOT NULL,
    referrer VARCHAR(255),
    country VARCHAR(2),
    device VARCHAR(16) NOT NULL DEFAULT 'unknown',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_web_analytics_event_name CHECK (
        event_name IN ('pageview', 'click', 'add_to_cart', 'begin_checkout', 'purchase')
    ),
    CONSTRAINT ck_web_analytics_device CHECK (
        device IN ('desktop', 'mobile', 'tablet', 'unknown')
    ),
    CONSTRAINT ck_web_analytics_country CHECK (
        country IS NULL OR country ~ '^[A-Z]{2}$'
    )
);

CREATE INDEX IF NOT EXISTS ix_web_analytics_created
    ON web_analytics_events (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_web_analytics_event_created
    ON web_analytics_events (event_name, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_web_analytics_visitor_created
    ON web_analytics_events (visitor_hash, created_at DESC);
