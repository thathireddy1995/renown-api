CREATE TABLE IF NOT EXISTS attributes (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    type VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT attributes_type_check CHECK (type IN ('select', 'boolean'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_attributes_name ON attributes (name);

CREATE TABLE IF NOT EXISTS attribute_values (
    id BIGSERIAL PRIMARY KEY,
    attribute_id BIGINT NOT NULL REFERENCES attributes (id) ON DELETE CASCADE,
    value VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_attribute_values_attribute_id ON attribute_values (attribute_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_attribute_values_attr_value
    ON attribute_values (attribute_id, value);
