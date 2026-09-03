from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from uuid import UUID
from typing import List
import logging

# Import the tools we need for security and database access
from ...core.auth import require_permission, require_any_permission, AuthenticatedUser, authenticate_request
from ...database import supabase

logger = logging.getLogger(__name__)

# Define the router for this section of the API
router = APIRouter(prefix="/departments", tags=["Departments"])


# --- Pydantic Models (Data Shapes) ---

# Defines the data needed to create a new department.
class DepartmentCreate(BaseModel):
    name: str
    label: str  # This is the unique string ID, e.g.,"customer-service"
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    show_in_sidebar: bool = True  # Controls visibility in sidebar Process Management menu


# Defines the data for updating an existing department. All fields are optional.
class DepartmentUpdate(BaseModel):
    name: str | None = None
    label: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    is_active: bool | None = None  # Added to support activate/deactivate
    sort_order: int | None = None   # Added to support reordering
    show_in_sidebar: bool | None = None  # Controls visibility in sidebar Process Management menu


# Defines the full department data that we will send back to the frontend.
class Department(BaseModel):
    id: UUID
    name: str
    label: str
    tenant_id: UUID
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    is_active: bool = True
    sort_order: int = 0
    show_in_sidebar: bool = True
    created_at: str
    updated_at: str | None = None


# Defines department data with user-specific visibility preference
class DepartmentWithPreference(BaseModel):
    id: UUID
    name: str
    label: str
    tenant_id: UUID
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    is_active: bool = True
    sort_order: int = 0
    show_in_sidebar: bool = True  # Global setting from departments table
    user_show_in_sidebar: bool = True  # User's personal preference
    created_at: str
    updated_at: str | None = None


# Defines the data for updating user's department visibility preference
class UserDepartmentPreferenceUpdate(BaseModel):
    show_in_sidebar: bool


# --- API Endpoints ---


@router.get("", response_model=List[Department])
async def list_departments(
    user: AuthenticatedUser = Depends(require_permission("departments", "read")),
):
    """
    Lists departments.
    - If the user is an admin, it lists all departments across all tenants.
    - Otherwise, it lists only the departments that belong to the authenticated user's tenant.
    """
    logger.debug("[list_departments] admin=%s", user.is_admin)
    
    query = supabase.table("departments").select("*")

    # Always filter by tenant for proper tenant isolation
    # Even admins should only see departments for their current tenant in User Management
    if user.tenant_id:
        query = query.eq("tenant_id", user.tenant_id)
        logger.debug("[list_departments] Applying tenant filter")
    else:
        logger.warning("[list_departments] Authenticated user has no tenant_id")

    try:
        result = query.execute()
        logger.info(f"[list_departments] Found {len(result.data)} departments")
        return result.data
    except Exception as e:
        logger.error(f"Failed to list departments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Department lookup is temporarily unavailable",
        )


@router.post("", response_model=Department, status_code=status.HTTP_201_CREATED)
async def create_department(
    dept_in: DepartmentCreate,
    # This endpoint is protected. Users need either "departments.create" OR "process_management.create" permission.
    user: AuthenticatedUser = Depends(require_any_permission(
        ("departments", "create"),
        ("process_management", "create")
    )),
):
    """
    Creates a new department for the authenticated user's tenant.
    Requires either departments.create OR process_management.create permission.
    """
    # we automatically stamp it with the user's tenant_id. It's impossible for a user
    # from Tenant A to create a department for Tenant B.
    department_data = dept_in.dict()
    department_data["tenant_id"] = user.tenant_id

    try:
        # Step 1: Insert the data. The response should contain the inserted row.
        insert_result = supabase.table("departments").insert(department_data).execute()

        # In supabase-py v2, exceptions are raised on HTTP error status codes.
        # We just need to check if the data is what we expect.
        if not insert_result.data:
            raise Exception("Database did not return the created department.")

        # The returned data should be a list with one element.
        new_department = insert_result.data[0]

        # The default representation might not include all fields (like updated_at).
        # To be safe and ensure compatibility with the response_model,
        # it's best to fetch the record again.
        new_department_id = new_department.get('id')
        if not new_department_id:
            raise Exception("Created department data did not include an ID.")

        # Fetch the complete record.
        fetch_result = supabase.table("departments").select("*").eq("id", new_department_id).single().execute()

        if not fetch_result.data:
            raise Exception(f"Could not retrieve the newly created department (ID: {new_department_id}).")

        return fetch_result.data
    except Exception as e:
        logger.error(f"Failed to create department: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The department could not be created",
        )


@router.put("/{department_id}", response_model=Department)
async def update_department(
    department_id: UUID,
    dept_in: DepartmentUpdate,
    user: AuthenticatedUser = Depends(require_any_permission(
        ("departments", "update"),
        ("process_management", "create")
    )),
):
    """
    Updates a department's details, ensuring it belongs to the user's tenant.
    Requires either departments.update OR process_management.create permission.
    """
    update_data = dept_in.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided",
        )

    try:
        # Step 1: Perform the update.
        update_result = (
            supabase.table("departments")
            .update(update_data)
            .eq("id", department_id)
            .eq("tenant_id", user.tenant_id) # Security check is part of the update
            .execute()
        )

        # If the update affects no rows (because the ID or tenant_id didn't match),
        # result.data will be empty.
        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found or you do not have access.",
            )

        # Step 2: Fetch the complete, updated record to return.
        select_result = (
            supabase.table("departments")
            .select("*")
            .eq("id", department_id)
            .single()
            .execute()
        )

        if not select_result.data:
            # This should not happen if the update succeeded, but it's a good safeguard.
            raise HTTPException(
                status_code=404,
                detail="Could not retrieve updated department.",
            )

        return select_result.data
    except Exception as e:
        logger.error(f"Failed to update department {department_id}: {e}")
        if "unique constraint" in str(e):
            status_code = status.HTTP_409_CONFLICT
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(
            status_code=status_code,
            detail="The department could not be updated",
        )


@router.delete("/{department_id}")
async def delete_department(
    department_id: UUID,
    user: AuthenticatedUser = Depends(require_any_permission(
        ("departments", "delete"),
        ("process_management", "create")
    )),
):
    """
    Deletes a department, ensuring it belongs to the user's tenant.
    Requires either departments.delete OR process_management.create permission.
    """
    try:
        # Atomically delete the row only if the tenant_id matches.
        result = (
            supabase.table("departments")
            .delete()
            .eq("id", department_id)
            .eq("tenant_id", user.tenant_id) # Security check is part of the delete
            .execute()
        )

        # If the delete affects no rows (because the ID or tenant_id didn't match),
        # result.data will be empty.
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found or you do not have access.",
            )

    except Exception as e:
        logger.error(f"Failed to delete department {department_id}: {e}")
        # This can happen if, for example, users are still assigned to this department.
        # The database's foreign key constraint will cause an error.
        if "foreign key constraint" in str(e):
            status_code = status.HTTP_409_CONFLICT
            detail = "Cannot delete department. It may still be in use (e.g., users are assigned to it)."
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            detail = "The department could not be deleted"
        raise HTTPException(status_code=status_code, detail=detail)

    return {"success": True, "message": "Department deleted successfully"}


@router.get("/my-departments", response_model=List[DepartmentWithPreference])
async def get_my_departments_with_preferences(
    user: AuthenticatedUser = Depends(authenticate_request),
):
    """
    Gets all departments assigned to the authenticated user with their personal visibility preferences.
    This endpoint is used in the Process Management page to show department cards with toggle controls.

    Admins see ALL departments in their tenant, regular users see only their assigned departments.
    Both can set personal visibility preferences.
    """
    logger.debug("[get_my_departments_with_preferences] admin=%s", user.is_admin)

    try:
        # If user is admin, get ALL departments in their tenant
        if user.is_admin:
            departments_result = (
                supabase.table("departments")
                .select("*")
                .eq("tenant_id", user.tenant_id)
                .eq("is_active", True)
                .order("sort_order")
                .execute()
            )

            if not departments_result.data:
                logger.info("[get_my_departments_with_preferences] No active departments found for administrator")
                return []

            department_ids = [dept["id"] for dept in departments_result.data]

            # Get admin's preferences for these departments
            preferences_result = (
                supabase.table("user_department_preferences")
                .select("department_id, show_in_sidebar")
                .eq("user_id", user.id)
                .in_("department_id", department_ids)
                .execute()
            )

            # Create a map of department_id -> user preference
            preferences_map = {}
            if preferences_result.data:
                preferences_map = {
                    pref["department_id"]: pref["show_in_sidebar"]
                    for pref in preferences_result.data
                }

            # Admins can have preferences too
            result = []
            for dept in departments_result.data:
                dept_id = dept["id"]
                # If admin has no preference set, default to True
                user_show_in_sidebar = preferences_map.get(dept_id, True)

                result.append({
                    **dept,
                    "user_show_in_sidebar": user_show_in_sidebar
                })

            logger.debug("[get_my_departments_with_preferences] Returning %d administrator departments", len(result))
            return result

        # For non-admin users, get their assigned departments
        user_departments_result = (
            supabase.table("user_departments")
            .select("department_id")
            .eq("user_id", user.id)
            .execute()
        )

        if not user_departments_result.data:
            logger.info("[get_my_departments_with_preferences] No assigned departments")
            return []

        department_ids = [row["department_id"] for row in user_departments_result.data]
        logger.debug("[get_my_departments_with_preferences] %d assigned departments", len(department_ids))

        # Get department details
        departments_result = (
            supabase.table("departments")
            .select("*")
            .in_("id", department_ids)
            .eq("tenant_id", user.tenant_id)
            .eq("is_active", True)  # Only show active departments
            .order("sort_order")
            .execute()
        )

        if not departments_result.data:
            logger.info("[get_my_departments_with_preferences] No active departments found")
            return []

        # Get user's preferences for these departments
        preferences_result = (
            supabase.table("user_department_preferences")
            .select("department_id, show_in_sidebar")
            .eq("user_id", user.id)
            .in_("department_id", department_ids)
            .execute()
        )

        # Create a map of department_id -> user preference
        preferences_map = {}
        if preferences_result.data:
            preferences_map = {
                pref["department_id"]: pref["show_in_sidebar"]
                for pref in preferences_result.data
            }

        # Combine department data with user preferences
        result = []
        for dept in departments_result.data:
            dept_id = dept["id"]
            # If user has no preference set, default to True
            user_show_in_sidebar = preferences_map.get(dept_id, True)

            result.append({
                **dept,
                "user_show_in_sidebar": user_show_in_sidebar
            })

        logger.debug("[get_my_departments_with_preferences] Returning %d departments", len(result))
        return result

    except Exception as e:
        logger.error(f"Failed to get user departments with preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Department lookup is temporarily unavailable",
        )


@router.put("/my-departments/{department_id}/preference")
async def update_my_department_preference(
    department_id: UUID,
    preference_in: UserDepartmentPreferenceUpdate,
    user: AuthenticatedUser = Depends(authenticate_request),
):
    """
    Updates the authenticated user's personal visibility preference for a specific department.
    This controls whether the department appears in their Process Management sidebar.

    Both admins and regular users can set their preferences.
    """
    logger.debug("[update_my_department_preference] Updating preference")

    try:
        # First verify that the department exists in the user's tenant
        dept_result = (
            supabase.table("departments")
            .select("id")
            .eq("id", department_id)
            .eq("tenant_id", user.tenant_id)
            .execute()
        )

        if not dept_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found in your tenant",
            )

        # For non-admin users, verify they have access to this department
        if not user.is_admin:
            user_dept_result = (
                supabase.table("user_departments")
                .select("department_id")
                .eq("user_id", user.id)
                .eq("department_id", department_id)
                .execute()
            )

            if not user_dept_result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Department not found or you do not have access to it",
                )

        # Check if preference already exists
        existing_pref_result = (
            supabase.table("user_department_preferences")
            .select("id")
            .eq("user_id", user.id)
            .eq("department_id", department_id)
            .execute()
        )

        preference_data = {
            "user_id": user.id,
            "department_id": str(department_id),
            "show_in_sidebar": preference_in.show_in_sidebar,
            "tenant_id": user.tenant_id
        }

        if existing_pref_result.data:
            # Update existing preference
            result = (
                supabase.table("user_department_preferences")
                .update({"show_in_sidebar": preference_in.show_in_sidebar})
                .eq("user_id", user.id)
                .eq("department_id", department_id)
                .execute()
            )
            logger.debug("[update_my_department_preference] Updated preference")
        else:
            # Create new preference
            result = (
                supabase.table("user_department_preferences")
                .insert(preference_data)
                .execute()
            )
            logger.debug("[update_my_department_preference] Created preference")

        if not result.data:
            raise Exception("Failed to update preference")

        return {
            "success": True,
            "message": "Department visibility preference updated successfully",
            "show_in_sidebar": preference_in.show_in_sidebar
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update department preference: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The department preference could not be updated",
        )
