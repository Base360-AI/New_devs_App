import { supabase } from "./supabase";
import { SecureAPI } from "./secureApi";
import { createLog } from "./logging";
import { Permission, CityId } from "../types/auth";
import { fetchUserById, getUserInfoSafely } from "./fetchUserById";

interface SignInResult {
    user: any;
    error: string | null;
    forcePasswordChange?: boolean;
}

// Define admin emails in one place for consistency
const ADMIN_EMAILS = [
    "sid@theflexliving.com",
    "raouf@theflexliving.com",
    "michael@theflexliving.com",
];

function isAdminEmail(email: string): boolean {
    return ADMIN_EMAILS.includes(email);
}

async function handleSuccessfulLogin(data: any): Promise<SignInResult> {
    console.log('[auth.ts] Step 2: Login successful, user authenticated');
    console.log('[auth.ts] Step 3: Now fetching bootstrap as FIRST API request...');

    const { fetchBootstrapDataRobust } = await import('../utils/robustBootstrapFetcher');

    try {
        console.log('[auth.ts] Calling fetchBootstrapDataRobust...');
        // Session is already established by the login call

        const bootstrapResult = await fetchBootstrapDataRobust();

        // Use bootstrap data for user context
        const bootstrapUser = bootstrapResult.data;
        const isAdmin = bootstrapUser?.user?.is_admin ||
            isAdminEmail(data.user.email || "") ||
            data.user.app_metadata?.role === "admin";

        const userCities = Array.isArray(bootstrapUser?.user?.cities)
            ? bootstrapUser.user.cities.map((city: string) => city.toLowerCase())
            : [];

        const forcePasswordChange =
            data.user.user_metadata?.force_password_change === true;

        console.log('[auth.ts] ===== SIGN IN COMPLETED =====');

        return {
            user: {
                ...data.user,
                permissions: bootstrapUser?.permissions || [],
                cities: userCities,
                isAdmin,
                tenant_id: bootstrapUser?.metadata?.tenant_id
            },
            error: null,
            forcePasswordChange,
        };
    } catch (bootstrapError) {
        console.error('[auth.ts] Bootstrap fetch failed, falling back to getAuthMe:', bootstrapError);

        // Fallback to the original getAuthMe if bootstrap fails
        const me = await SecureAPI.getAuthMe();

        const isAdmin = me.is_admin ||
            isAdminEmail(data.user.email || "") ||
            data.user.app_metadata?.role === "admin";
        const userCities = Array.isArray(me.cities)
            ? me.cities.map(city => city.toLowerCase())
            : [];

        return {
            user: {
                ...data.user,
                permissions: me.permissions || [],
                cities: userCities,
                isAdmin,
            },
            error: null,
            forcePasswordChange: data.user.user_metadata?.force_password_change === true,
        };
    }
}

export async function signIn(
    email: string,
    password: string,
): Promise<SignInResult> {
    try {
        console.log('[auth.ts] ===== SIGN IN STARTED =====');

        const cleanEmail = email.trim();
        const cleanPassword = password.trim();

        console.log('[auth.ts] Checking credentials for:', cleanEmail);

        console.log('[auth.ts] Step 1: Calling backend login...');

        const { user, session, error } = await supabase.auth.signInWithPassword({
            email: cleanEmail,
            password: cleanPassword,
        });

        if (error) throw error;

        const data = { user, session };

        return await handleSuccessfulLogin(data);

    } catch (error: any) {
        console.error("Sign in error:", error);
        return { user: null, error: error.message };
    }
}

export async function signOut() {
    try {
        const { error } = await supabase.auth.signOut();
        if (error) throw error;
    } catch (error: any) {
        console.error("Sign out error:", error);
        throw error;
    }
}

export async function getCurrentUser() {
    try {
        const {
            data: { session },
        } = await supabase.auth.getSession();
        if (!session?.user) return null;

        console.log("Getting current user permissions for:", session.user.id);

        // Fetch consolidated user context from backend
        const me = await SecureAPI.getAuthMe();
        const isAdmin = me.is_admin ||
            isAdminEmail(session.user.email || "") ||
            session.user.app_metadata?.role === "admin";
        // Ensure cities are always lowercase for consistency
        const userCities = Array.isArray(me.cities)
            ? me.cities.map(city => city.toLowerCase())
            : [];

        // For admin emails, ensure they have key management permissions
        const userPermissions = me.permissions || [];
        if (isAdminEmail(session.user.email || "")) {
            const keyPermissions = [
                { section: "lockbox", action: "create" },
                { section: "lockbox", action: "read" },
                { section: "lockbox", action: "update" },
                { section: "lockbox", action: "delete" },
                { section: "lockbox", action: "modify_status_only" },
                { section: "internal_keys", action: "create" },
                { section: "internal_keys", action: "read" },
                { section: "internal_keys", action: "update" },
                { section: "internal_keys", action: "delete" },
                { section: "internal_keys", action: "modify_status_only" },
                { section: "keynest", action: "create" },
                { section: "keynest", action: "read" },
                { section: "keynest", action: "update" },
                { section: "keynest", action: "delete" },
            ];

            // Add key permissions if they don't already exist
            keyPermissions.forEach((keyPerm) => {
                if (
                    !userPermissions.some(
                        (p) => p.section === keyPerm.section && p.action === keyPerm.action,
                    )
                ) {
                    userPermissions.push(keyPerm);
                }
            });
        }

        const currentUser = {
            ...session.user,
            permissions: userPermissions,
            cities: userCities,
            isAdmin,
        };

        console.log("Current user with permissions:", {
            id: currentUser.id,
            email: currentUser.email,
            permissions_count: currentUser.permissions.length,
            cities_count: currentUser.cities.length,
            is_admin: currentUser.isAdmin,
        });

        return currentUser;
    } catch (error) {
        console.error("Error getting current user:", error);
        return null;
    }
}

export async function changePassword(newPassword: string) {
    try {
        const { data, error } = await supabase.auth.updateUser({
            password: newPassword,
            data: { force_password_change: false },
        });

        if (error) throw error;

        await createLog({
            action: "update",
            section: "auth",
            entity_type: "user",
            entity_id: data.user.id,
            context: "Password changed successfully",
        });

        return { error: null };
    } catch (error: any) {
        console.error("Error changing password:", error);
        return { error: error.message };
    }
}

export async function createUser({
    email,
    password,
    name,
    phone,
    department,
    permissions,
    cities,
    isAdmin = false,
}: {
    email: string;
    password: string;
    name: string;
    phone?: string;
    department?: string;
    permissions: Permission[];
    cities: CityId[];
    isAdmin?: boolean;
}) {
    try {
        // Remove email domain validation - allow any email domain

        // Validate phone number format if provided
        if (phone && !phone.match(/^\+[1-9]\d{1,14}$/)) {
            throw new Error(
                "Please enter a valid phone number in international format (e.g., +447123456789)",
            );
        }

        // Validate cities (keep minimal client-side validation; backend enforces tenant rules)
        if (!Array.isArray(cities)) {
            throw new Error("Cities must be an array");
        }

        // Check if user is admin email - always admin
        if (isAdminEmail(email)) {
            isAdmin = true;
        }

        console.log("Creating user with data:", {
            email,
            name,
            phone,
            department,
            isAdmin,
            cities: cities.length,
            permissions: permissions.length,
        });

        // Get current session for authentication
        const {
            data: { session },
        } = await supabase.auth.getSession();
        if (!session) {
            throw new Error("No active session");
        }

        // Create user through backend API
        const BACKEND_URL =
            import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
        const response = await fetch(`${BACKEND_URL}/api/v1/users`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${session.access_token}`,
            },
            body: JSON.stringify({
                email,
                password,
                name,
                phone: phone || null,
                department: department || null,
                isAdmin,
                permissions,
                cities,
            }),
        });

        if (!response.ok) {
            const errorData = await response
                .json()
                .catch(() => ({ detail: "Unknown error occurred" }));
            throw new Error(
                errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
            );
        }

        const result = await response.json();
        const userId = result.userId;

        console.log("User created successfully via backend API:", {
            userId,
            email,
        });

        // Log the creation
        await createLog({
            action: "create",
            section: "users",
            entity_type: "user",
            entity_id: userId,
            context: `Created new user: ${name} (${email})`,
            metadata: {
                isAdmin,
                permissionCount: permissions.length,
                cityCount: cities.length,
                cities,
            },
        });

        // Send welcome email
        try {
            const response = await fetch(
                `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/send-welcome-email`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${import.meta.env.VITE_SUPABASE_ANON_KEY}`,
                    },
                    body: JSON.stringify({
                        email,
                        name,
                    }),
                },
            );

            if (!response.ok) {
                console.warn(
                    "Failed to send welcome email, but user was created successfully",
                );
            }
        } catch (emailError) {
            console.error("Error sending welcome email:", emailError);
            // Don't throw error - user is still created successfully
        }

        return { userId, error: null };
    } catch (error: any) {
        console.error("Error creating user:", error);
        return { userId: null, error: error.message };
    }
}

export async function getUserPermissionsDetails(userId: string) {
    try {
        console.log("Fetching permissions details for user:", userId);

        // Get user's permissions with a direct query (allowed in dev allowlist)
        const { data: permissions, error: permissionsError } = await supabase
            .from("user_permissions")
            .select("section, action")
            .eq("user_id", userId);

        if (permissionsError) {
            console.error("Error fetching permissions:", permissionsError);
            throw new Error(
                `Failed to fetch permissions: ${permissionsError.message}`,
            );
        }

        console.log("Fetched permissions:", permissions);

        // Get user's city access (allowed in dev allowlist)
        const { data: cities, error: citiesError } = await supabase
            .from("users_city")
            .select("city_name")
            .eq("user_id", userId);

        if (citiesError) {
            console.error("Error fetching cities:", citiesError);
            throw new Error(`Failed to fetch cities: ${citiesError.message}`);
        }

        console.log("Fetched cities:", cities);

        // Get the current user's session to check if they're viewing themselves
        const { data: { session } } = await supabase.auth.getSession();

        let userEmail = "";
        let userName = "";
        let isAdmin = false;
        let userCreatedAt = "";
        let userStatus = "active";
        let backendUserData: any = null;

        const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

        let allowedCitiesResponse: any[] = [];
        const allowedCityMap = new Map<string, string>();

        if (session?.access_token) {
            try {
                // Use tenant-scoped filters endpoint for cities
                const allowedResp = await fetch(`${BACKEND_URL}/api/v1/filters/cities`, {
                    headers: {
                        Authorization: `Bearer ${session.access_token}`,
                        "Content-Type": "application/json",
                    },
                });

                if (allowedResp.ok) {
                    const json = await allowedResp.json();
                    // Expect { success: true, data: [{ value, label }, ...] }
                    allowedCitiesResponse = Array.isArray(json?.data) ? json.data : [];
                } else {
                    console.warn(
                        "Failed to fetch allowed cities, status:",
                        allowedResp.status,
                    );
                }
            } catch (cityError) {
                console.error("Error fetching allowed cities:", cityError);
            }
        }

        // Build allowed city map from filters response (value is the city slug)
        allowedCitiesResponse.forEach((opt: any) => {
            const rawCity = (opt?.value || "").trim();
            if (!rawCity) return;
            const key = rawCity.toLowerCase();
            if (!allowedCityMap.has(key)) {
                allowedCityMap.set(key, key);
            }
        });
        const allowedCitiesList = Array.from(allowedCityMap.values());

        // If viewing self, we have more data from session
        if (session?.user?.id === userId) {
            userEmail = session.user.email || "";
            userName = session.user.user_metadata?.name || userEmail.split("@")[0];
            userCreatedAt = session.user.created_at || "";
            isAdmin = session.user.app_metadata?.role === "admin" || isAdminEmail(userEmail);
            userStatus = session.user.user_metadata?.status || "active";
        } else {
            // For other users, fetch their actual data from backend
            try {
                const response = await fetch(`${BACKEND_URL}/api/v1/users/${userId}`, {
                    headers: {
                        Authorization: `Bearer ${session?.access_token}`,
                    },
                });

                if (response.ok) {
                    backendUserData = await response.json();
                    userEmail = backendUserData.email || `User ${userId.slice(0, 8)}`;
                    userName = backendUserData.user_metadata?.name || backendUserData.name || userEmail.split("@")[0];
                    userCreatedAt = backendUserData.created_at || "";
                    // Check both app_metadata.role and the isAdmin field
                    isAdmin = backendUserData.app_metadata?.role === "admin" ||
                        backendUserData.isAdmin === true ||
                        backendUserData.tenant_role === "admin" ||
                        isAdminEmail(backendUserData.email || "");
                    userStatus = backendUserData.user_metadata?.status || backendUserData.status || "active";
                } else {
                    // Fallback if we can't get user data
                    isAdmin = permissions?.some(p => p.section === "*" && p.action === "*") || false;
                    userEmail = `User ${userId.slice(0, 8)}`;
                    userName = userEmail;
                    userCreatedAt = new Date().toISOString();
                    userStatus = "active";
                }
            } catch (error) {
                console.error("Error fetching user details:", error);
                // Fallback values
                isAdmin = permissions?.some(p => p.section === "*" && p.action === "*") || false;
                userEmail = `User ${userId.slice(0, 8)}`;
                userName = userEmail;
                userCreatedAt = new Date().toISOString();
                userStatus = "active";
            }
        }

        const tenantRole = (session?.user?.app_metadata as any)?.tenant_role
            || (typeof backendUserData?.tenant_role === 'string' ? backendUserData.tenant_role : undefined)
            || (isAdmin ? 'admin' : 'member');

        const allowedCityKeySet = new Set(Array.from(allowedCityMap.keys()));

        const rawCityList = (cities || [])
            .map((c) => (c.city_name || '').trim())
            .filter((city) => !!city);

        const filteredUserCities = allowedCityKeySet.size > 0
            ? rawCityList
                .filter((city) => allowedCityKeySet.has(city.toLowerCase()))
                .map((city) => allowedCityMap.get(city.toLowerCase()) || city)
            : rawCityList;

        const normalizedAllowedCities = allowedCitiesList.length > 0 ? allowedCitiesList : filteredUserCities;

        const userCities = isAdmin
            ? normalizedAllowedCities
            : filteredUserCities;

        // Format the response
        const permissionsDetails = {
            user: {
                id: userId,
                email: userEmail,
                name: userName,
                created_at: userCreatedAt,
                last_sign_in_at: "",
                user_metadata: {},
                app_metadata: {},
                isAdmin: isAdmin,
                tenant_role: tenantRole,
                permissions: permissions || [],
                cities: userCities,
                status: userStatus,
            },
            permissions: permissions || [],
            cities: userCities,
            metadata: {
                total_permissions: permissions?.length || 0,
                total_cities: userCities.length,
                is_admin: isAdmin,
                allowed_cities: normalizedAllowedCities,
            },
        };

        console.log("Formatted permissions details:", permissionsDetails);

        // Log the permissions check
        await createLog({
            action: "read",
            section: "permissions",
            entity_type: "user",
            entity_id: userId,
            context: `Retrieved permissions details for user ${userId}`,
            metadata: {
                permissions_count: permissionsDetails.metadata.total_permissions,
                cities_count: permissionsDetails.metadata.total_cities,
                is_admin: isAdmin,
            },
        });

        return permissionsDetails;
    } catch (error: any) {
        console.error("Error getting user permissions details:", error);
        throw new Error(`Failed to get user permissions: ${error.message}`);
    }
}

export async function updateUser(
    userId: string,
    updateData: any,
): Promise<{ error: string | null }> {
    try {
        // Get current permissions for logging
        const currentPermissions = await getUserPermissionsDetails(userId);

        const allowedCitiesFromMetadata: string[] =
            currentPermissions?.metadata?.allowed_cities || [];
        const allowedCityMap = new Map<string, string>();
        allowedCitiesFromMetadata.forEach((city) => {
            if (!city) return;
            allowedCityMap.set(city.toLowerCase(), city);
        });

        // Get current session for authentication
        const {
            data: { session },
        } = await supabase.auth.getSession();
        if (!session) {
            throw new Error("No active session");
        }

        // Separate update data into user_metadata and app_metadata
        const userMetadata: any = {};
        const appMetadata: any = {};

        const isAdmin = updateData.isAdmin === true;
        const hasCitySelection = Array.isArray(updateData.cities);
        const sanitizedCities = hasCitySelection
            ? (allowedCityMap.size > 0
                ? updateData.cities
                    .filter((city: string) =>
                        typeof city === 'string' && allowedCityMap.has(city.toLowerCase())
                    )
                    .map((city: string) => allowedCityMap.get(city.toLowerCase()) || city)
                : updateData.cities)
            : null;

        // User metadata fields
        if (updateData.name !== undefined) userMetadata.name = updateData.name;
        if (updateData.phone !== undefined) userMetadata.phone = updateData.phone;
        if (updateData.department !== undefined) userMetadata.department = updateData.department;
        if (updateData.status !== undefined) userMetadata.status = updateData.status;

        // App metadata fields
        if (updateData.isAdmin !== undefined) appMetadata.role = isAdmin ? "admin" : "user";
        // Note: permissions and cities are handled separately in their respective tables (user_permissions and users_city)
        // They should NOT be stored in app_metadata to avoid size limits

        // Update user metadata through backend API if provided
        if (Object.keys(userMetadata).length > 0 || Object.keys(appMetadata).length > 0 || updateData.password) {
            const BACKEND_URL =
                import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

            const updatePayload: any = {};
            if (Object.keys(userMetadata).length > 0) {
                updatePayload.user_metadata = userMetadata;
            }
            if (Object.keys(appMetadata).length > 0) {
                updatePayload.app_metadata = appMetadata;
            }
            if (updateData.password) {
                updatePayload.password = updateData.password;
            }

            // Add phone to top-level if provided in userMetadata
            if (userMetadata.phone) {
                updatePayload.phone = userMetadata.phone;
            }

            // Add permissions and cities to the payload if provided
            if (updateData.permissions) {
                updatePayload.permissions = updateData.permissions.map((p: Permission) => ({
                    section: p.section,
                    action: p.action,
                }));
            }
            if (isAdmin) {
                updatePayload.cities = [];
            } else if (hasCitySelection) {
                updatePayload.cities = sanitizedCities || [];
            }

            // Add departments to the payload if provided
            if (updateData.departments !== undefined) {
                updatePayload.departments = updateData.departments;
            }

            console.log("Sending update payload to backend:", updatePayload);

            const response = await fetch(`${BACKEND_URL}/api/v1/users/${userId}`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${session.access_token}`,
                },
                body: JSON.stringify(updatePayload),
            });

            if (!response.ok) {
                const errorData = await response
                    .json()
                    .catch(() => ({ detail: "Failed to update user" }));
                console.error("Backend error response:", errorData);
                throw new Error(
                    errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
                );
            }
        }

        // Update permissions if provided (these are in allowed tables)
        if (updateData.permissions) {
            // First delete existing permissions
            const { error: deleteError } = await supabase
                .from("user_permissions")
                .delete()
                .eq("user_id", userId);

            if (deleteError) throw deleteError;

            // Then insert new permissions if any are provided
            if (updateData.permissions.length > 0) {
                const { error: insertError } = await supabase
                    .from("user_permissions")
                    .insert(
                        updateData.permissions.map((p: Permission) => ({
                            user_id: userId,
                            section: p.section,
                            action: p.action,
                        })),
                    );

                if (insertError) throw insertError;
            }
        }

        // Update cities if provided (these are in allowed tables)
        if (isAdmin) {
            const { error: deleteCitiesError } = await supabase
                .from("users_city")
                .delete()
                .eq("user_id", userId);

            if (deleteCitiesError) throw deleteCitiesError;
        } else if (hasCitySelection) {
            const { error: deleteCitiesError } = await supabase
                .from("users_city")
                .delete()
                .eq("user_id", userId);

            if (deleteCitiesError) throw deleteCitiesError;

            if ((sanitizedCities || []).length > 0) {
                const { error: insertCitiesError } = await supabase
                    .from("users_city")
                    .insert(
                        (sanitizedCities as string[]).map((city: string) => ({
                            user_id: userId,
                            city_name: city,
                        })),
                    );

                if (insertCitiesError) throw insertCitiesError;
            }
        }

        // Get updated permissions for comparison
        const updatedPermissions = await getUserPermissionsDetails(userId);

        // Log the update with detailed changes
        await createLog({
            action: "update",
            section: "users",
            entity_type: "user",
            entity_id: userId,
            context: "Updated user profile, permissions, and city access",
            field_name: "permissions",
            old_value: currentPermissions,
            new_value: updatedPermissions,
            metadata: {
                user_metadata: userMetadata,
                app_metadata: appMetadata,
                update_data: updateData,
                changes: {
                    permissions_changed:
                        currentPermissions.metadata.total_permissions !==
                        updatedPermissions.metadata.total_permissions,
                    cities_changed:
                        currentPermissions.metadata.total_cities !==
                        updatedPermissions.metadata.total_cities,
                },
            },
        });

        return { error: null };
    } catch (error: any) {
        console.error("Error updating user:", error);
        return { error: error.message };
    }
}
