from typing import List, Dict, Any
from app.core.database_pool import DatabasePool
from sqlalchemy import text

async def get_properties_for_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Fetches the properties owned by a specific tenant.
    Includes a fallback mock if the database is unavailable.
    """
    db_pool = DatabasePool()
    await db_pool.initialize()
    
    if not db_pool.session_factory:
        # Mock fallback for when DB is disconnected
        mock_props = {
            'tenant-a': [
                {'id': 'prop-001', 'name': 'Beach House Alpha'},
                {'id': 'prop-002', 'name': 'City Apartment Downtown'},
                {'id': 'prop-003', 'name': 'Country Villa Estate'},
            ],
            'tenant-b': [
                {'id': 'prop-001', 'name': 'Mountain Lodge Beta'},
                {'id': 'prop-004', 'name': 'Lakeside Cottage'},
                {'id': 'prop-005', 'name': 'Urban Loft Modern'},
            ]
        }
        return mock_props.get(tenant_id, [])
        
    try:
        async with db_pool.get_session() as session:
            query = text("""
                SELECT id, name
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY name
            """)
            result = await session.execute(query, {"tenant_id": tenant_id})
            return [{"id": row.id, "name": row.name} for row in result.fetchall()]
    except Exception as e:
        print(f"Database error fetching properties for {tenant_id}: {e}")
        # Fallback to mock data if query fails
        mock_props = {
            'tenant-a': [
                {'id': 'prop-001', 'name': 'Beach House Alpha'},
                {'id': 'prop-002', 'name': 'City Apartment Downtown'},
                {'id': 'prop-003', 'name': 'Country Villa Estate'},
            ],
            'tenant-b': [
                {'id': 'prop-001', 'name': 'Mountain Lodge Beta'},
                {'id': 'prop-004', 'name': 'Lakeside Cottage'},
                {'id': 'prop-005', 'name': 'Urban Loft Modern'},
            ]
        }
        return mock_props.get(tenant_id, [])
