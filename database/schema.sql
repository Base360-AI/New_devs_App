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
    tenant_id TEXT REFERENCES tenants(id),
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (id, tenant_id)
);

-- Reservations Table
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    property_id TEXT,
    tenant_id TEXT REFERENCES tenants(id),
    check_in_date TIMESTAMP WITH TIME ZONE NOT NULL,
    check_out_date TIMESTAMP WITH TIME ZONE NOT NULL,
    total_amount NUMERIC(10, 3) NOT NULL, -- storing as numeric with 3 decimals to allow sub-cent precision tracking
    currency TEXT DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (property_id, tenant_id) REFERENCES properties(id, tenant_id)
);

-- RLS Policies
-- The backend connects as app_user (not a superuser, so RLS cannot be bypassed)
-- and sets app.current_tenant for every transaction.
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE reservations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_properties ON properties
    USING (tenant_id = current_setting('app.current_tenant', true));

CREATE POLICY tenant_isolation_reservations ON reservations
    USING (tenant_id = current_setting('app.current_tenant', true));

CREATE ROLE app_user LOGIN PASSWORD 'app_user';
GRANT SELECT ON tenants, properties, reservations TO app_user;
