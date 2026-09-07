from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from ...database import supabase
from ...core.tenant_resolver import TenantResolver
from ...models.auth import Permission
import logging
import hashlib
from datetime import datetime, timedelta
import jwt
from ...config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    error: Optional[str] = None

ADMIN_EMAILS = [
    "sid@theflexliving.com",
    "raouf@theflexliving.com", 
    "michael@theflexliving.com",
    "candidate@propertyflow.com"
]

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login endpoint for local authentication"""
    try:
        email = request.email.lower().strip()
        password = request.password.strip()
        
        logger.info(f"[LOGIN] Attempting login for: {email}")
        
        # Static credentials - Tenant A.
        if email == "sunset@propertyflow.com" and password == "client_a_2024":
            logger.info("[LOGIN] Challenge Mode: Tenant A (Sunset Properties)")
            
            # Create mock JWT token
            user_data = {
                "id": "user-sunset",
                "email": "sunset@propertyflow.com",
                "app_metadata": {"role": "user", "tenant_id": "tenant-a"},
                "user_metadata": {"name": "Sunset Properties Manager"},
                "aud": "authenticated",
                "created_at": datetime.utcnow().isoformat(),
                "exp": datetime.utcnow() + settings.access_token_expire_timedelta
            }
            
            token = jwt.encode(user_data, settings.secret_key, algorithm="HS256")
            
            return LoginResponse(
                access_token=token,
                user={
                    "id": "user-sunset",
                    "email": "sunset@propertyflow.com",
                    "name": "Sunset Properties Manager",
                    "is_admin": False,
                    "tenant_id": "tenant-a",
                    "permissions": [],
                    "cities": []
                }
            )
            
        # Static credentials - Tenant B.
        if email == "ocean@propertyflow.com" and password == "client_b_2024":
            logger.info("[LOGIN] Challenge Mode: Tenant B (Ocean Rentals)")
            
            # Create mock JWT token
            user_data = {
                "id": "user-ocean",
                "email": "ocean@propertyflow.com",
                "app_metadata": {"role": "user", "tenant_id": "tenant-b"},
                "user_metadata": {"name": "Ocean Rentals Manager"},
                "aud": "authenticated",
                "created_at": datetime.utcnow().isoformat(),
                "exp": datetime.utcnow() + settings.access_token_expire_timedelta
            }
            
            token = jwt.encode(user_data, settings.secret_key, algorithm="HS256")
            
            return LoginResponse(
                access_token=token,
                user={
                    "id": "user-ocean",
                    "email": "ocean@propertyflow.com",
                    "name": "Ocean Rentals Manager",
                    "is_admin": False,
                    "tenant_id": "tenant-b",
                    "permissions": [],
                    "cities": []
                }
            )
        
        # For other users, check if they exist in the database
        # This is a simplified auth - in production you'd check password hashes
        try:
            # Check if user exists in Supabase auth
            user_result = supabase.auth.admin.list_users()
            users = user_result if hasattr(user_result, '__iter__') else []
            
            user = None
            for u in users:
                if u.email and u.email.lower() == email:
                    user = u
                    break
                    
            if not user:
                logger.warning(f"[LOGIN] User not found: {email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )
            
            # Get user permissions
            permissions_response = (
                supabase.service.table("user_permissions")
                .select("section, action")
                .eq("user_id", user.id)
                .execute()
            )
            permissions = [Permission(**perm) for perm in permissions_response.data]
            
            # Get user cities  
            cities_response = (
                supabase.service.table("users_city")
                .select("city_name")
                .eq("user_id", user.id)
                .execute()
            )
            user_cities = [city["city_name"].lower() for city in cities_response.data if city.get("city_name")]
            
            # Check admin status
            is_admin = (
                user.email in ADMIN_EMAILS or 
                (user.app_metadata and user.app_metadata.get("role") == "admin")
            )
            
            # Resolve tenant ID
            tenant_id = await TenantResolver.resolve_tenant_id(user_id=user.id, user_email=user.email)
            
            # Create JWT token
            user_data = {
                "id": user.id,
                "email": user.email,
                "is_admin": is_admin,
                "tenant_id": tenant_id,
                "exp": datetime.utcnow() + settings.access_token_expire_timedelta,
                "aud": "authenticated"
            }
            
            token = jwt.encode(user_data, settings.secret_key, algorithm="HS256")
            
            logger.info(f"[LOGIN] Success for {email}")
            
            return LoginResponse(
                access_token=token,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.user_metadata.get("name", email.split("@")[0]) if user.user_metadata else email.split("@")[0],
                    "is_admin": is_admin,
                    "tenant_id": tenant_id,
                    "permissions": [{"section": p.section, "action": p.action} for p in permissions],
                    "cities": user_cities
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[LOGIN] Database error for {email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LOGIN] Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/logout")
async def logout():
    """Logout endpoint"""
    # For JWT-based auth, logout is handled client-side by removing token
    return {"message": "Logged out successfully"}
