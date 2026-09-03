from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import time
from ...core.auth import authenticate_request, has_permission
from ...database import supabase
from ...models.auth import AuthenticatedUser
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory cache for company settings
company_settings_cache: Dict[str, Any] = {}
CACHE_TTL = 300  # 5 minutes in seconds

def get_tenant_default_name(tenant_id: str) -> str:
    """Get tenant-aware default company name based on tenant ID"""
    # Known tenant mappings for proper branding
    tenant_defaults = {
        "5a382f72-aec3-40f1-9063-89476ae00669": "Homely",  # Homely tenant
        "a860bda4-b44f-471c-9464-8456bbeb7d38": "The Flex",  # The Flex tenant
    }
    return tenant_defaults.get(tenant_id, "Base360")  # Neutral default

def get_tenant_default_branding(tenant_id: str) -> dict:
    """Get tenant-aware default branding colors and settings"""
    # Tenant-specific branding
    tenant_branding = {
        "5a382f72-aec3-40f1-9063-89476ae00669": {  # Homely
            "header_color": "#2C5F2D",
            "primary_color": "#E8F5E8", 
            "secondary_color": "#F5FDF5",
            "accent_color": "#2C5F2D",
        },
        "a860bda4-b44f-471c-9464-8456bbeb7d38": {  # The Flex
            "header_color": "#284E4C",
            "primary_color": "#FFF9E9",
            "secondary_color": "#FFFDF6", 
            "accent_color": "#284E4C",
        }
    }
    
    return tenant_branding.get(tenant_id, {
        "header_color": "#1a1a1a",  # Neutral defaults
        "primary_color": "#ffffff",
        "secondary_color": "#f5f5f5",
        "accent_color": "#0066cc",
    })

class CompanySettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    domain: Optional[str] = None
    header_color: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    favicon_url: Optional[str] = None
    availability_days_back: Optional[int] = None
    availability_days_ahead: Optional[int] = None

@router.get("/company-settings")
async def get_company_settings(
    current_user: AuthenticatedUser = Depends(authenticate_request)
):
    """Get company settings for the user's tenant"""
    try:
        # Get tenant_id
        tenant_id = current_user.tenant_id
        
        # Check cache first
        cache_key = f"company_settings:{tenant_id}"
        if cache_key in company_settings_cache:
            cached_data = company_settings_cache[cache_key]
            if cached_data['timestamp'] + CACHE_TTL > time.time():
                logger.info(f"Returning cached company settings for tenant {tenant_id}")
                return cached_data['data']
            else:
                # Cache expired, remove it
                del company_settings_cache[cache_key]
        
        logger.debug("Fetching company settings")
        
        if not tenant_id:
            # Fallback: get from user_tenants using service role to avoid RLS edge cases
            tenant_result = (
                supabase.service
                .table('user_tenants')
                .select('tenant_id')
                .eq('user_id', current_user.id)
                .eq('is_active', True)
                .maybe_single()
                .execute()
            )
            if getattr(tenant_result, 'data', None):
                tenant_id = tenant_result.data.get('tenant_id')
            else:
                logger.warning("No tenant found for authenticated user")
                # Return neutral default settings (no caching for no-tenant case)
                return {
                    "company_name": "Base360",  # Neutral default, not tenant-specific
                    "logo_url": None,
                    "domain": None,
                    "header_color": "#1a1a1a",  # Neutral colors
                    "primary_color": "#ffffff",
                    "secondary_color": "#f5f5f5",
                    "accent_color": "#0066cc",
                    "favicon_url": None,
                    "availability_days_back": 3,
                    "availability_days_ahead": 7,
                    "tenant_id": None
                }
        
        # Query settings for this tenant
        # Fetch settings with service role (safe because tenant_id was derived from membership)
        result = (
            supabase.service
            .table('company_settings')
            .select('*')
            .eq('tenant_id', tenant_id)
            .maybe_single()
            .execute()
        )
        
        if result.data:
            logger.info(f"Found company settings for tenant {tenant_id}")
            # Cache the result
            company_settings_cache[cache_key] = {
                'data': result.data,
                'timestamp': time.time()
            }
            return result.data
        else:
            logger.info(f"No company settings found for tenant {tenant_id}, returning defaults")
            # Try to get tenant name for default
            tenant_result = (
                supabase.service
                .table('tenants')
                .select('name')
                .eq('id', tenant_id)
                .maybe_single()
                .execute()
            )
            # Get tenant-aware default name based on tenant ID
            tenant_data = getattr(tenant_result, 'data', {}) or {}
            default_name = get_tenant_default_name(tenant_id)
            tenant_name = tenant_data.get('name') or default_name
            
            # Get tenant-aware branding defaults
            branding = get_tenant_default_branding(tenant_id)
            
            # Return default settings with tenant-specific branding
            default_settings = {
                "company_name": tenant_name,
                "logo_url": None,
                "domain": None,
                "header_color": branding["header_color"],
                "primary_color": branding["primary_color"],
                "secondary_color": branding["secondary_color"],
                "accent_color": branding["accent_color"],
                "favicon_url": None,
                "availability_days_back": 3,
                "availability_days_ahead": 7,
                "tenant_id": str(tenant_id)
            }
            
            # Cache the default settings too
            company_settings_cache[cache_key] = {
                'data': default_settings,
                'timestamp': time.time()
            }
            
            return default_settings
        
    except Exception as e:
        logger.error(f"Error fetching company settings: {str(e)}")
        # Return neutral defaults on error - avoid tenant-specific data when system fails
        return {
            "company_name": "Base360",  # Neutral fallback
            "logo_url": None,
            "domain": None,
            "header_color": "#1a1a1a",  # Neutral colors
            "primary_color": "#ffffff",
            "secondary_color": "#f5f5f5",
            "accent_color": "#0066cc",
            "favicon_url": None,
            "availability_days_back": 3,
            "availability_days_ahead": 7,
            "tenant_id": None
        }

@router.put("/company-settings")
async def update_company_settings(
    settings: CompanySettingsUpdate,
    current_user: AuthenticatedUser = Depends(authenticate_request)
):
    """Update company settings for the user's tenant"""
    try:
        # Check permissions
        if not has_permission(current_user, "settings", "write"):
            raise HTTPException(status_code=403, detail="Insufficient permissions to update settings")
        
        logger.info("Updating company settings")
        
        # Get tenant_id
        tenant_id = current_user.tenant_id
        
        # Invalidate cache for this tenant
        cache_key = f"company_settings:{tenant_id}"
        if cache_key in company_settings_cache:
            del company_settings_cache[cache_key]
        if not tenant_id:
            # Fallback: get from user_tenants
            tenant_result = supabase.table('user_tenants').select('tenant_id').eq('user_id', current_user.id).eq('is_active', True).execute()
            if tenant_result.data and len(tenant_result.data) > 0:
                tenant_id = tenant_result.data[0]['tenant_id']
            else:
                raise HTTPException(status_code=400, detail="No tenant found for user")
        
        # Prepare update data
        update_data = {
            "tenant_id": tenant_id,
            "updated_at": datetime.now().isoformat()
        }
        
        # Add non-null fields from the update request
        if settings.company_name is not None:
            update_data["company_name"] = settings.company_name
        if settings.logo_url is not None:
            update_data["logo_url"] = settings.logo_url
        if settings.domain is not None:
            update_data["domain"] = settings.domain
        if settings.header_color is not None:
            update_data["header_color"] = settings.header_color
        if settings.primary_color is not None:
            update_data["primary_color"] = settings.primary_color
        if settings.secondary_color is not None:
            update_data["secondary_color"] = settings.secondary_color
        if settings.accent_color is not None:
            update_data["accent_color"] = settings.accent_color
        if settings.favicon_url is not None:
            update_data["favicon_url"] = settings.favicon_url
        if settings.availability_days_back is not None:
            update_data["availability_days_back"] = settings.availability_days_back
        if settings.availability_days_ahead is not None:
            update_data["availability_days_ahead"] = settings.availability_days_ahead
        
        # Use upsert to handle both insert and update
        result = supabase.service.table('company_settings').upsert(
            update_data,
            on_conflict='tenant_id'
        ).execute()
        
        if result.data:
            logger.info(f"Successfully updated company settings for tenant {tenant_id}")
            return {"success": True, "settings": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to update settings")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating company settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/company-settings/logo")
async def upload_company_logo(
    logo_data: Dict[str, Any],
    current_user: AuthenticatedUser = Depends(authenticate_request)
):
    """Upload company logo"""
    try:
        # Check permissions
        if not has_permission(current_user, "settings", "write"):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Get tenant_id
        tenant_id = current_user.tenant_id
        if not tenant_id:
            tenant_result = supabase.table('user_tenants').select('tenant_id').eq('user_id', current_user.id).eq('is_active', True).execute()
            if tenant_result.data:
                tenant_id = tenant_result.data[0]['tenant_id']
            else:
                raise HTTPException(status_code=400, detail="No tenant found")
        
        # Here you would handle logo upload to storage
        # For now, just update the logo_url in settings
        logo_url = logo_data.get("logo_url")
        
        if not logo_url:
            raise HTTPException(status_code=400, detail="No logo URL provided")
        
        # Update settings with new logo
        result = supabase.service.table('company_settings').upsert({
            "tenant_id": tenant_id,
            "logo_url": logo_url,
            "updated_at": datetime.now().isoformat()
        }, on_conflict='tenant_id').execute()
        
        return {"success": True, "logo_url": logo_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading logo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/company-settings/logo")
async def delete_company_logo(
    current_user: AuthenticatedUser = Depends(authenticate_request)
):
    """Delete company logo"""
    try:
        # Check permissions
        if not has_permission(current_user, "settings", "write"):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Get tenant_id
        tenant_id = current_user.tenant_id
        if not tenant_id:
            tenant_result = supabase.table('user_tenants').select('tenant_id').eq('user_id', current_user.id).eq('is_active', True).execute()
            if tenant_result.data:
                tenant_id = tenant_result.data[0]['tenant_id']
            else:
                raise HTTPException(status_code=400, detail="No tenant found")
        
        # Update settings to remove logo
        result = supabase.service.table('company_settings').update({
            "logo_url": None,
            "updated_at": datetime.now().isoformat()
        }).eq('tenant_id', tenant_id).execute()
        
        return {"success": True, "message": "Logo deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting logo: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
