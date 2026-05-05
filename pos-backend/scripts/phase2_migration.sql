BEGIN;

-- Running upgrade 0004 -> 0005

CREATE TABLE pos_users (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE RESTRICT, 
    UNIQUE (email)
);

CREATE INDEX ix_pos_users_brand_id ON pos_users (brand_id);

CREATE UNIQUE INDEX ix_pos_users_email ON pos_users (email);

CREATE TABLE access_profiles (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    is_system BOOLEAN DEFAULT false NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE RESTRICT
);

CREATE INDEX ix_access_profiles_brand_id ON access_profiles (brand_id);

CREATE TABLE user_access_grants (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    access_profile_id UUID NOT NULL, 
    granted_by_id UUID, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES pos_users (id) ON DELETE CASCADE, 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
    FOREIGN KEY(access_profile_id) REFERENCES access_profiles (id) ON DELETE RESTRICT, 
    FOREIGN KEY(granted_by_id) REFERENCES pos_users (id) ON DELETE SET NULL
);

CREATE INDEX ix_user_access_grants_user_id ON user_access_grants (user_id);

CREATE INDEX ix_user_access_grants_site_id ON user_access_grants (site_id);

CREATE TABLE user_invites (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    access_profile_id UUID NOT NULL, 
    invited_by_id UUID, 
    email VARCHAR(255) NOT NULL, 
    token VARCHAR(255) NOT NULL, 
    is_accepted BOOLEAN DEFAULT false NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE, 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
    FOREIGN KEY(access_profile_id) REFERENCES access_profiles (id) ON DELETE RESTRICT, 
    FOREIGN KEY(invited_by_id) REFERENCES pos_users (id) ON DELETE SET NULL, 
    UNIQUE (token)
);

CREATE INDEX ix_user_invites_brand_id ON user_invites (brand_id);

CREATE INDEX ix_user_invites_email ON user_invites (email);

CREATE UNIQUE INDEX ix_user_invites_token ON user_invites (token);

CREATE TABLE user_pins (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    pin_hash VARCHAR(255) NOT NULL, 
    is_pin_reset_required BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (user_id), 
    FOREIGN KEY(user_id) REFERENCES pos_users (id) ON DELETE CASCADE
);

CREATE TABLE user_pos_sessions (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    token_jti VARCHAR(36) NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    ended_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES pos_users (id) ON DELETE CASCADE, 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
    UNIQUE (token_jti)
);

CREATE INDEX ix_user_pos_sessions_user_id ON user_pos_sessions (user_id);

CREATE INDEX ix_user_pos_sessions_site_id ON user_pos_sessions (site_id);

CREATE UNIQUE INDEX ix_user_pos_sessions_token_jti ON user_pos_sessions (token_jti);

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

CREATE TABLE tax_categories (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE
);

CREATE INDEX ix_tax_categories_brand_id ON tax_categories (brand_id);

CREATE TABLE tax_rates (
    id UUID NOT NULL, 
    tax_category_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    rate_percent NUMERIC(10, 4) NOT NULL, 
    tax_model VARCHAR(20) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(tax_category_id) REFERENCES tax_categories (id) ON DELETE CASCADE
);

CREATE INDEX ix_tax_rates_tax_category_id ON tax_rates (tax_category_id);

ALTER TABLE categories ADD COLUMN tax_category_id UUID;

ALTER TABLE categories ADD FOREIGN KEY(tax_category_id) REFERENCES tax_categories (id) ON DELETE SET NULL;

ALTER TABLE categories ADD COLUMN description TEXT;

ALTER TABLE categories ADD COLUMN image_url VARCHAR(1024);

ALTER TABLE categories ADD COLUMN display_order INTEGER DEFAULT '0' NOT NULL;

ALTER TABLE categories ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

CREATE TABLE products (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    category_id UUID NOT NULL, 
    tax_category_id UUID, 
    name VARCHAR(255) NOT NULL, 
    description TEXT, 
    base_price_cents BIGINT NOT NULL, 
    photo_url VARCHAR(1024), 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE RESTRICT, 
    FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT, 
    FOREIGN KEY(tax_category_id) REFERENCES tax_categories (id) ON DELETE SET NULL
);

CREATE INDEX ix_products_brand_id ON products (brand_id);

CREATE INDEX ix_products_category_id ON products (category_id);

CREATE TABLE site_product_overrides (
    id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    override_price_cents BIGINT, 
    is_excluded BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_site_product_overrides_site_id ON site_product_overrides (site_id);

CREATE INDEX ix_site_product_overrides_product_id ON site_product_overrides (product_id);

ALTER TABLE site_product_overrides ADD CONSTRAINT uq_site_product_overrides_site_product UNIQUE (site_id, product_id);

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

-- Running upgrade 0006 -> 0007

CREATE TABLE product_attribute_types (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_attribute_types_brand_id ON product_attribute_types (brand_id);

CREATE TABLE product_attribute_values (
    id UUID NOT NULL, 
    attribute_type_id UUID NOT NULL, 
    value VARCHAR(100) NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(attribute_type_id) REFERENCES product_attribute_types (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_attribute_values_type_id ON product_attribute_values (attribute_type_id);

CREATE TABLE product_variants (
    id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    sku VARCHAR(100), 
    price_cents BIGINT, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_variants_product_id ON product_variants (product_id);

CREATE TABLE product_variant_attributes (
    variant_id UUID NOT NULL, 
    attribute_type_id UUID NOT NULL, 
    attribute_value_id UUID NOT NULL, 
    CONSTRAINT pk_product_variant_attributes PRIMARY KEY (variant_id, attribute_type_id), 
    FOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE CASCADE, 
    FOREIGN KEY(attribute_type_id) REFERENCES product_attribute_types (id) ON DELETE RESTRICT, 
    FOREIGN KEY(attribute_value_id) REFERENCES product_attribute_values (id) ON DELETE RESTRICT
);

CREATE TABLE site_variant_overrides (
    id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    variant_id UUID NOT NULL, 
    override_price_cents BIGINT, 
    is_excluded BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE CASCADE, 
    FOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE CASCADE
);

CREATE INDEX ix_site_variant_overrides_site_id ON site_variant_overrides (site_id);

CREATE INDEX ix_site_variant_overrides_variant_id ON site_variant_overrides (variant_id);

ALTER TABLE site_variant_overrides ADD CONSTRAINT uq_site_variant_overrides_site_variant UNIQUE (site_id, variant_id);

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

-- Running upgrade 0007 -> 0008

CREATE TABLE modifier_groups (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    min_selections INTEGER DEFAULT '0' NOT NULL, 
    max_selections INTEGER DEFAULT '1' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE
);

CREATE INDEX ix_modifier_groups_brand_id ON modifier_groups (brand_id);

CREATE TABLE modifier_options (
    id UUID NOT NULL, 
    modifier_group_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    price_delta_cents BIGINT DEFAULT '0' NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(modifier_group_id) REFERENCES modifier_groups (id) ON DELETE CASCADE
);

CREATE INDEX ix_modifier_options_group_id ON modifier_options (modifier_group_id);

CREATE TABLE product_modifier_group_links (
    id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    modifier_group_id UUID NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
    FOREIGN KEY(modifier_group_id) REFERENCES modifier_groups (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_modifier_group_links_product_id ON product_modifier_group_links (product_id);

CREATE TABLE product_combo_groups (
    id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    min_selections INTEGER DEFAULT '1' NOT NULL, 
    max_selections INTEGER DEFAULT '1' NOT NULL, 
    is_required BOOLEAN DEFAULT true NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_combo_groups_product_id ON product_combo_groups (product_id);

CREATE TABLE product_combo_options (
    id UUID NOT NULL, 
    combo_group_id UUID NOT NULL, 
    product_id UUID NOT NULL, 
    price_delta_cents BIGINT DEFAULT '0' NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(combo_group_id) REFERENCES product_combo_groups (id) ON DELETE CASCADE, 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_combo_options_combo_group_id ON product_combo_options (combo_group_id);

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';

-- Running upgrade 0008 -> 0009

CREATE TABLE invoices (
    id UUID NOT NULL, 
    brand_id UUID NOT NULL, 
    site_id UUID NOT NULL, 
    created_by_id UUID, 
    invoice_type VARCHAR(20) DEFAULT 'sale' NOT NULL, 
    status VARCHAR(20) DEFAULT 'draft' NOT NULL, 
    subtotal_cents BIGINT DEFAULT '0' NOT NULL, 
    tax_cents BIGINT DEFAULT '0' NOT NULL, 
    discount_cents BIGINT DEFAULT '0' NOT NULL, 
    discount_reason VARCHAR(255), 
    total_cents BIGINT DEFAULT '0' NOT NULL, 
    refund_of_id UUID, 
    is_refunded BOOLEAN DEFAULT false NOT NULL, 
    voided_at TIMESTAMP WITH TIME ZONE, 
    paid_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE RESTRICT, 
    FOREIGN KEY(site_id) REFERENCES sites (id) ON DELETE RESTRICT, 
    FOREIGN KEY(created_by_id) REFERENCES pos_users (id) ON DELETE SET NULL
);

ALTER TABLE invoices ADD CONSTRAINT fk_invoices_refund_of_id FOREIGN KEY(refund_of_id) REFERENCES invoices (id) ON DELETE SET NULL;

CREATE INDEX ix_invoices_brand_id ON invoices (brand_id);

CREATE INDEX ix_invoices_site_id ON invoices (site_id);

CREATE TABLE invoice_line_items (
    id UUID NOT NULL, 
    invoice_id UUID NOT NULL, 
    product_id UUID, 
    product_name VARCHAR(255) NOT NULL, 
    unit_price_cents BIGINT NOT NULL, 
    tax_category_name VARCHAR(100), 
    tax_rate_percent NUMERIC(10, 4) DEFAULT '0' NOT NULL, 
    tax_model VARCHAR(20) DEFAULT 'exclusive' NOT NULL, 
    quantity INTEGER DEFAULT '1' NOT NULL, 
    subtotal_cents BIGINT DEFAULT '0' NOT NULL, 
    tax_cents BIGINT DEFAULT '0' NOT NULL, 
    line_total_cents BIGINT DEFAULT '0' NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, 
    FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE SET NULL
);

CREATE INDEX ix_invoice_line_items_invoice_id ON invoice_line_items (invoice_id);

CREATE TABLE invoice_line_modifiers (
    id UUID NOT NULL, 
    line_item_id UUID NOT NULL, 
    modifier_option_id UUID, 
    modifier_name VARCHAR(100) NOT NULL, 
    price_delta_cents BIGINT DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(line_item_id) REFERENCES invoice_line_items (id) ON DELETE CASCADE, 
    FOREIGN KEY(modifier_option_id) REFERENCES modifier_options (id) ON DELETE SET NULL
);

CREATE INDEX ix_invoice_line_modifiers_line_item_id ON invoice_line_modifiers (line_item_id);

CREATE TABLE invoice_tax_breakdowns (
    id UUID NOT NULL, 
    invoice_id UUID NOT NULL, 
    tax_rate_id UUID, 
    tax_rate_name VARCHAR(100) NOT NULL, 
    rate_percent NUMERIC(10, 4) NOT NULL, 
    tax_model VARCHAR(20) NOT NULL, 
    taxable_amount_cents BIGINT DEFAULT '0' NOT NULL, 
    tax_amount_cents BIGINT DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, 
    FOREIGN KEY(tax_rate_id) REFERENCES tax_rates (id) ON DELETE SET NULL
);

CREATE INDEX ix_invoice_tax_breakdowns_invoice_id ON invoice_tax_breakdowns (invoice_id);

CREATE TABLE payments (
    id UUID NOT NULL, 
    invoice_id UUID NOT NULL, 
    method VARCHAR(20) NOT NULL, 
    amount_cents BIGINT NOT NULL, 
    reference VARCHAR(255), 
    paid_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
);

CREATE INDEX ix_payments_invoice_id ON payments (invoice_id);

UPDATE alembic_version SET version_num='0009' WHERE alembic_version.version_num = '0008';

-- Running upgrade 0009 -> 0010

CREATE VIEW vw_daily_sales AS
        SELECT
            i.brand_id,
            i.site_id,
            DATE(i.created_at) AS sale_date,
            COUNT(*) AS invoice_count,
            COALESCE(SUM(i.subtotal_cents), 0) AS subtotal_cents,
            COALESCE(SUM(i.tax_cents), 0) AS tax_cents,
            COALESCE(SUM(i.discount_cents), 0) AS discount_cents,
            COALESCE(SUM(i.total_cents), 0) AS total_cents
        FROM invoices i
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY i.brand_id, i.site_id, DATE(i.created_at);

CREATE VIEW vw_product_revenue AS
        SELECT
            ili.product_id,
            ili.product_name,
            i.brand_id,
            i.site_id,
            SUM(ili.quantity) AS total_units,
            COALESCE(SUM(ili.subtotal_cents), 0) AS revenue_cents,
            COALESCE(SUM(ili.tax_cents), 0) AS tax_cents
        FROM invoice_line_items ili
        JOIN invoices i ON ili.invoice_id = i.id
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY ili.product_id, ili.product_name, i.brand_id, i.site_id;

CREATE VIEW vw_payment_methods AS
        SELECT
            p.method,
            i.brand_id,
            i.site_id,
            COUNT(*) AS payment_count,
            COALESCE(SUM(p.amount_cents), 0) AS total_amount_cents
        FROM payments p
        JOIN invoices i ON p.invoice_id = i.id
        WHERE i.invoice_type = 'sale'
        GROUP BY p.method, i.brand_id, i.site_id;

CREATE VIEW vw_tax_collected AS
        SELECT
            itb.tax_rate_name,
            itb.rate_percent,
            itb.tax_model,
            i.brand_id,
            i.site_id,
            COALESCE(SUM(itb.taxable_amount_cents), 0) AS taxable_amount_cents,
            COALESCE(SUM(itb.tax_amount_cents), 0) AS tax_amount_cents
        FROM invoice_tax_breakdowns itb
        JOIN invoices i ON itb.invoice_id = i.id
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY itb.tax_rate_name, itb.rate_percent, itb.tax_model, i.brand_id, i.site_id;

CREATE VIEW vw_hourly_sales AS
        SELECT
            i.brand_id,
            i.site_id,
            EXTRACT(HOUR FROM i.created_at)::INTEGER AS hour_of_day,
            COUNT(*) AS invoice_count,
            COALESCE(SUM(i.total_cents), 0) AS total_cents
        FROM invoices i
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY i.brand_id, i.site_id, EXTRACT(HOUR FROM i.created_at);

CREATE VIEW vw_modifier_popularity AS
        SELECT
            ilm.modifier_name,
            i.brand_id,
            COUNT(*) AS usage_count,
            COALESCE(SUM(ilm.price_delta_cents), 0) AS total_revenue_impact_cents
        FROM invoice_line_modifiers ilm
        JOIN invoice_line_items ili ON ilm.line_item_id = ili.id
        JOIN invoices i ON ili.invoice_id = i.id
        WHERE i.status = 'paid' AND i.invoice_type = 'sale'
        GROUP BY ilm.modifier_name, i.brand_id;

CREATE VIEW vw_invoice_detail AS
        SELECT
            i.id,
            i.brand_id,
            i.site_id,
            i.created_by_id,
            i.invoice_type,
            i.status,
            i.subtotal_cents,
            i.tax_cents,
            i.discount_cents,
            i.total_cents,
            i.refund_of_id,
            i.is_refunded,
            i.voided_at,
            i.paid_at,
            i.created_at,
            s.name AS site_name,
            b.name AS brand_name
        FROM invoices i
        JOIN sites s ON i.site_id = s.id
        JOIN brands b ON i.brand_id = b.id;

CREATE VIEW vw_refund_summary AS
        SELECT
            i.brand_id,
            i.site_id,
            DATE(i.created_at) AS refund_date,
            COUNT(*) AS refund_count,
            COALESCE(SUM(ABS(i.total_cents)), 0) AS refund_total_cents
        FROM invoices i
        WHERE i.invoice_type = 'refund'
        GROUP BY i.brand_id, i.site_id, DATE(i.created_at);

UPDATE alembic_version SET version_num='0010' WHERE alembic_version.version_num = '0009';

COMMIT;

