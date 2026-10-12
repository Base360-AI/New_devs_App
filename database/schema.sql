-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants Table
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Properties Table
CREATE TABLE properties (
    id TEXT NOT NULL, -- Not PK solely, might be composite with tenant in real world, but strict ID here
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (id, tenant_id)
);

-- Reservations Table
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    check_in_date TIMESTAMP WITH TIME ZONE NOT NULL,
    check_out_date TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(10, 3) NOT NULL, -- storing as numeric with 3 decimals to allow sub-cent precision tracking
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (property_id, tenant_id) REFERENCES properties(id, tenant_id)
);

-- RLS: every row is visible only to the tenant set via set_config('app.tenant_id', ...).
-- Unset setting -> current_setting returns NULL -> no rows (fails closed).
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties FORCE ROW LEVEL SECURITY;
ALTER TABLE reservations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON properties
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON reservations
    USING (tenant_id = current_setting('app.tenant_id', true));

-- The app connects as this role. Superusers (postgres) bypass RLS, so the app must not use one.
CREATE ROLE app_user LOGIN PASSWORD 'app_user' NOSUPERUSER NOBYPASSRLS;
GRANT SELECT ON tenants, properties, reservations TO app_user;
