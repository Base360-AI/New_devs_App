-- Move the hardcoded admin / tenant-user emails into the database.
-- Additive on purpose: the ADMIN_EMAILS lists in auth.py, login.py, bootstrap.py
-- and users_lightning.py stay exactly as they are. Callers should treat this as a
-- second source and OR the two together, so nothing breaks if the table is empty.
--
-- Idempotent: safe to run more than once.
--   docker exec -i new_devs_app-db-1 psql -U postgres -d propertyflow < sql/create_admin_user_tables.sql

-- Admin allow-list
CREATE TABLE IF NOT EXISTS app_admins (
    email TEXT PRIMARY KEY,
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tenant users (identity + tenant mapping only; no credentials stored here yet)
CREATE TABLE IF NOT EXISTS app_tenant_users (
    email TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT REFERENCES tenants(id),
    name TEXT,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_tenant_users_tenant ON app_tenant_users (tenant_id);

-- Seed with the emails currently hardcoded in Python (union of all four lists)
INSERT INTO app_admins (email, note) VALUES
    ('sid@theflexliving.com',      'from core/auth.py'),
    ('raouf@theflexliving.com',    'from core/auth.py'),
    ('michael@theflexliving.com',  'from core/auth.py'),
    ('younes@gmail.com',           'from core/auth.py'),
    ('yazid@theflexliving.com',    'from core/auth.py'),
    ('candidate@propertyflow.com', 'from api/v1/login.py')
ON CONFLICT (email) DO NOTHING;

INSERT INTO app_tenant_users (email, user_id, tenant_id, name) VALUES
    ('sunset@propertyflow.com', 'user-sunset', 'tenant-a', 'Sunset Properties Manager'),
    ('ocean@propertyflow.com',  'user-ocean',  'tenant-b', 'Ocean Rentals Manager')
ON CONFLICT (email) DO NOTHING;

-- Lookup helpers

CREATE OR REPLACE FUNCTION is_app_admin(p_email TEXT)
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM app_admins WHERE lower(email) = lower(trim(p_email))
    ) OR EXISTS (
        SELECT 1 FROM app_tenant_users
        WHERE lower(email) = lower(trim(p_email)) AND is_admin
    );
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION get_tenant_user(p_email TEXT)
RETURNS TABLE (email TEXT, user_id TEXT, tenant_id TEXT, name TEXT, is_admin BOOLEAN) AS $$
    SELECT u.email, u.user_id, u.tenant_id, u.name,
           u.is_admin OR is_app_admin(u.email)
    FROM app_tenant_users u
    WHERE lower(u.email) = lower(trim(p_email));
$$ LANGUAGE sql STABLE;

-- Verify
SELECT 'app_admins' AS table_name, count(*) AS rows FROM app_admins
UNION ALL
SELECT 'app_tenant_users', count(*) FROM app_tenant_users;

SELECT is_app_admin('sid@theflexliving.com')  AS should_be_true,
       is_app_admin('sunset@propertyflow.com') AS should_be_false;

SELECT * FROM get_tenant_user('ocean@propertyflow.com');
