export interface UserProfile {
  id: string;
  user_id: string;
  display_name?: string;
  bio?: string;
  phone?: string;
  department?: string;
  job_title?: string;
  location?: string;
  timezone: string;
  language: string;
  theme: string;
  avatar_url?: string;
  created_at: string;
  updated_at: string;
}

export interface UserPreferences {
  id: string;
  user_id: string;
  notification_email: boolean;
  notification_push: boolean;
  notification_desktop: boolean;
  notification_sound: boolean;
  auto_refresh: boolean;
  compact_view: boolean;
  sidebar_collapsed: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationPreference {
  id: string;
  user_id: string;
  category: string;
  email_enabled: boolean;
  push_enabled: boolean;
  desktop_enabled: boolean;
  sound_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileResponse {
  profile: UserProfile;
  preferences: UserPreferences;
  notification_preferences: NotificationPreference[];
  unread_count: number;
}

export interface ProfileUpdateRequest {
  display_name?: string;
  bio?: string;
  phone?: string;
  department?: string;
  job_title?: string;
  location?: string;
  timezone?: string;
  language?: string;
  theme?: string;
}

export interface PreferencesUpdateRequest {
  notification_email?: boolean;
  notification_push?: boolean;
  notification_desktop?: boolean;
  notification_sound?: boolean;
  auto_refresh?: boolean;
  compact_view?: boolean;
  sidebar_collapsed?: boolean;
}

export interface NotificationPreferenceUpdateRequest {
  email_enabled?: boolean;
  push_enabled?: boolean;
  desktop_enabled?: boolean;
  sound_enabled?: boolean;
}

export interface AvatarUploadResponse {
  avatar_url: string;
  message: string;
}


export interface property {
  property_id: string;
  name: string;
}