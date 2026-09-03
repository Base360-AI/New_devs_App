from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from ...database import supabase
from ...core.auth import authenticate_request

router = APIRouter()

@router.get("/cities")
async def get_available_cities(current_user = Depends(authenticate_request)):
    """
    Get all available cities from the properties table.
    Returns cities that have at least one active property.
    Results are restricted to the authenticated tenant.
    """
    try:
        # Query to get distinct cities from properties table where status is active
        result = supabase.table('properties') \
            .select('city') \
            .eq('tenant_id', current_user.tenant_id) \
            .neq('city', '') \
            .not_.is_('city', 'null') \
            .eq('status', 'active') \
            .execute()
        
        # Group cities and count properties
        city_counts = {}
        for row in result.data:
            city = row['city']
            if city:
                city_name = city.lower().strip()
                if city_name:
                    city_counts[city_name] = city_counts.get(city_name, 0) + 1
        
        cities = []
        for city_name, count in sorted(city_counts.items()):
            cities.append({
                'id': city_name,
                'name': city_name.title(),
                'property_count': count
            })
        
        return {
            'cities': cities,
            'total': len(cities)
        }
        
    except Exception as e:
        print(f"Error fetching cities: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cities")

@router.get("/cities/user-accessible")
async def get_user_accessible_cities(
    current_user = Depends(authenticate_request)
):
    """
    Get cities that the current user has access to.
    Admins get all cities, regular users get their assigned cities.
    """
    try:
        user_id = current_user.id
        user_email = current_user.email
        
        # Check if user is admin (same logic as auth.py)
        is_admin = current_user.is_admin
        
        if is_admin:
            # Admin gets all available cities
            result = supabase.table('properties') \
                .select('city') \
                .eq('tenant_id', current_user.tenant_id) \
                .neq('city', '') \
                .not_.is_('city', 'null') \
                .eq('status', 'active') \
                .execute()
            
            # Group cities and count properties
            city_counts = {}
            for row in result.data:
                city = row['city']
                if city:
                    city_name = city.lower().strip()
                    if city_name:
                        city_counts[city_name] = city_counts.get(city_name, 0) + 1
        else:
            # Regular user gets only their assigned cities that have active properties
            # First get user's accessible cities
            user_cities_result = supabase.table('users_city') \
                .select('city_name') \
                .eq('user_id', user_id) \
                .execute()
            
            accessible_cities = [row['city_name'].lower() for row in user_cities_result.data]
            
            if accessible_cities:
                # Get properties in accessible cities
                result = supabase.table('properties') \
                    .select('city') \
                    .eq('tenant_id', current_user.tenant_id) \
                    .neq('city', '') \
                    .not_.is_('city', 'null') \
                    .eq('status', 'active') \
                    .execute()
                
                # Filter and count cities
                city_counts = {}
                for row in result.data:
                    city = row['city']
                    if city:
                        city_name = city.lower().strip()
                        if city_name in accessible_cities:
                            city_counts[city_name] = city_counts.get(city_name, 0) + 1
            else:
                city_counts = {}
        
        cities = []
        for city_name, count in sorted(city_counts.items()):
            cities.append({
                'id': city_name,
                'name': city_name.title(),
                'property_count': count
            })
        
        return {
            'cities': cities,
            'total': len(cities),
            'is_admin': is_admin
        }
        
    except Exception as e:
        print(f"Error fetching user accessible cities: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch accessible cities")
