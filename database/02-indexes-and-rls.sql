-- Indexes for the revenue read path and the tenant-isolation policies that
-- schema.sql enables but never defines. Safe to re-run.

-- Revenue queries filter on (tenant_id, property_id); the monthly view also
-- ranges over check_in_date. Without these the table is a sequential scan.
CREATE INDEX IF NOT EXISTS idx_reservations_tenant_property
    ON reservations (tenant_id, property_id);

CREATE INDEX IF NOT EXISTS idx_reservations_tenant_property_checkin
    ON reservations (tenant_id, property_id, check_in_date);

CREATE INDEX IF NOT EXISTS idx_properties_tenant
    ON properties (tenant_id);

-- schema.sql enables RLS on these tables but ships no policies. These filter on
-- an app.current_tenant setting the application sets per connection. They stay
-- inert until the app connects as a non-superuser role (postgres bypasses RLS),
-- so apply this together with that role change, not on its own.
DROP POLICY IF EXISTS tenant_isolation_properties ON properties;
CREATE POLICY tenant_isolation_properties ON properties
    USING (tenant_id = current_setting('app.current_tenant', true));

DROP POLICY IF EXISTS tenant_isolation_reservations ON reservations;
CREATE POLICY tenant_isolation_reservations ON reservations
    USING (tenant_id = current_setting('app.current_tenant', true));
