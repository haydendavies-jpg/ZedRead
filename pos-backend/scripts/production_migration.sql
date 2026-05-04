BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE groups (
    id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

COMMENT ON COLUMN groups.id IS 'Primary key — UUID generated at insert time';

COMMENT ON COLUMN groups.is_active IS 'False when the group is suspended';

CREATE TABLE brands (
    id UUID NOT NULL, 
    group_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE RESTRICT
);

CREATE INDEX ix_brands_group_id ON brands (group_id);

CREATE TABLE sites (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE RESTRICT
);

CREATE INDEX ix_sites_brand_id ON sites (brand_id);

CREATE TABLE audit_logs (
    id UUID NOT NULL, 
    actor_id UUID, 
    actor_type VARCHAR(20) NOT NULL, 
    actor_email VARCHAR(255), 
    actor_name VARCHAR(255), 
    action VARCHAR(100) NOT NULL, 
    entity_type VARCHAR(100) NOT NULL, 
    entity_id VARCHAR(100) NOT NULL, 
    before_state JSONB, 
    after_state JSONB, 
    request_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

COMMENT ON COLUMN audit_logs.actor_id IS 'Null for system-generated audit rows (Celery tasks etc.)';

COMMENT ON COLUMN audit_logs.actor_type IS '''user'' or ''system''';

COMMENT ON COLUMN audit_logs.actor_email IS 'Snapshotted at time of action';

COMMENT ON COLUMN audit_logs.actor_name IS 'Snapshotted at time of action';

COMMENT ON COLUMN audit_logs.action IS 'Dot-separated action constant, e.g. ''group.created''';

COMMENT ON COLUMN audit_logs.entity_id IS 'String-cast PK of the affected row';

COMMENT ON COLUMN audit_logs.request_id IS 'UUID from X-Request-ID — links this row to the HTTP request';

CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id);

CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE TABLE portal_users (
    id UUID NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    role VARCHAR(50) DEFAULT 'admin' NOT NULL, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_portal_users_email ON portal_users (email);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TABLE categories (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    is_system BOOLEAN DEFAULT 'false' NOT NULL, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE
);

CREATE INDEX ix_categories_brand_id ON categories (brand_id);

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TABLE licenses (
    id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    plan_name VARCHAR(100) NOT NULL, 
    status VARCHAR(20) DEFAULT 'active' NOT NULL, 
    monthly_fee_cents BIGINT NOT NULL, 
    is_trial BOOLEAN DEFAULT 'false' NOT NULL, 
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_licenses_site_id UNIQUE (site_id)
);

CREATE INDEX ix_licenses_site_id ON licenses (site_id);

CREATE TABLE license_invoices (
    id UUID NOT NULL, 
    license_id UUID NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    status VARCHAR(20) DEFAULT 'open' NOT NULL, 
    period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
    period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
    paid_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(license_id) REFERENCES licenses (id) ON DELETE RESTRICT
);

CREATE INDEX ix_license_invoices_license_id ON license_invoices (license_id);

CREATE TABLE pos_devices (
    id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    license_id UUID NOT NULL, 
    device_name VARCHAR(255) NOT NULL, 
    device_token VARCHAR(255) NOT NULL, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(license_id) REFERENCES licenses (id) ON DELETE RESTRICT, 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pos_devices_device_token UNIQUE (device_token)
);

CREATE INDEX ix_pos_devices_site_id ON pos_devices (site_id);

CREATE INDEX ix_pos_devices_license_id ON pos_devices (license_id);

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

COMMIT;

