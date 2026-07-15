-- INSERT TENANTS
INSERT INTO tenants (id, name) VALUES 
    ('tenant-a', 'Sunset Properties'),
    ('tenant-b', 'Ocean Rentals');

-- INSERT PROPERTIES
INSERT INTO properties (id, tenant_id, name, timezone) VALUES
    ('prop-001', 'tenant-a', 'Beach House Alpha', 'Europe/Paris'),
    ('prop-001', 'tenant-b', 'Mountain Lodge Beta', 'America/New_York'),
    ('prop-002', 'tenant-a', 'City Apartment Downtown', 'Europe/Paris'),
    ('prop-003', 'tenant-a', 'Country Villa Estate', 'Europe/Paris'),
    ('prop-004', 'tenant-b', 'Lakeside Cottage', 'America/New_York'),
    ('prop-005', 'tenant-b', 'Urban Loft Modern', 'America/New_York');

-- INSERT RESERVATIONS

-- Sample reservation data (tenant-a).
INSERT INTO reservations (id, property_id, tenant_id, check_in_date, check_out_date, total_amount) VALUES
    ('res-tz-1', 'prop-001', 'tenant-a', '2024-02-29 23:30:00+00', '2024-03-05 10:00:00+00', 1250.000);

-- Additional sample reservation data.
-- Additional sample reservation data.
INSERT INTO reservations (id, property_id, tenant_id, check_in_date, check_out_date, total_amount) VALUES
    -- prop-001: Beach House Alpha (tenant-a)
    ('res-dec-1', 'prop-001', 'tenant-a', '2024-03-15 10:00:00+00', '2024-03-18 10:00:00+00', 333.333),
    ('res-dec-2', 'prop-001', 'tenant-a', '2024-03-16 10:00:00+00', '2024-03-19 10:00:00+00', 333.333),
    ('res-dec-3', 'prop-001', 'tenant-a', '2024-03-17 10:00:00+00', '2024-03-20 10:00:00+00', 333.334),
    
    -- prop-002: City Apartment Downtown (tenant-a) - High-value urban property
    ('res-004', 'prop-002', 'tenant-a', '2024-03-05 14:00:00+00', '2024-03-08 11:00:00+00', 1250.00),
    ('res-005', 'prop-002', 'tenant-a', '2024-03-12 16:00:00+00', '2024-03-15 10:00:00+00', 1475.50),
    ('res-006', 'prop-002', 'tenant-a', '2024-03-20 15:00:00+00', '2024-03-23 12:00:00+00', 1199.25),
    ('res-007', 'prop-002', 'tenant-a', '2024-03-25 18:00:00+00', '2024-03-28 14:00:00+00', 1050.75),
    ('res-cents-demo', 'prop-002', 'tenant-a', '2024-03-10 12:00:00+00', '2024-03-12 12:00:00+00', 0.005),
    
    -- prop-003: Country Villa Estate (tenant-a) - Luxury property with highest rates
    ('res-008', 'prop-003', 'tenant-a', '2024-03-02 15:00:00+00', '2024-03-09 12:00:00+00', 2850.00),
    ('res-009', 'prop-003', 'tenant-a', '2024-03-18 16:00:00+00', '2024-03-25 11:00:00+00', 3250.50),
    
    -- prop-004: Lakeside Cottage (tenant-b) - Mid-range seasonal property  
    ('res-010', 'prop-004', 'tenant-b', '2024-03-08 18:00:00+00', '2024-03-11 15:00:00+00', 420.00),
    ('res-011', 'prop-004', 'tenant-b', '2024-03-14 17:00:00+00', '2024-03-18 14:00:00+00', 560.75),
    ('res-012', 'prop-004', 'tenant-b', '2024-03-22 16:00:00+00', '2024-03-26 13:00:00+00', 480.25),
    ('res-013', 'prop-004', 'tenant-b', '2024-03-28 19:00:00+00', '2024-03-31 15:00:00+00', 315.50),
    
    -- prop-005: Urban Loft Modern (tenant-b) - Premium downtown loft
    ('res-014', 'prop-005', 'tenant-b', '2024-03-06 19:00:00+00', '2024-03-10 16:00:00+00', 920.00),
    ('res-015', 'prop-005', 'tenant-b', '2024-03-15 18:00:00+00', '2024-03-19 17:00:00+00', 1080.40),
    ('res-016', 'prop-005', 'tenant-b', '2024-03-24 20:00:00+00', '2024-03-29 14:00:00+00', 1255.60);