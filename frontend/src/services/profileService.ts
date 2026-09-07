import { supabase } from '../lib/supabase';
import { 
  ProfileResponse, 
  ProfileUpdateRequest, 
  PreferencesUpdateRequest, 
  NotificationPreferenceUpdateRequest,
  AvatarUploadResponse
} from '../types/profile';
import { getApiBase } from '../lib/apiBase';

class ProfileService {
  private async getAuthHeaders() {
    const { data: { session } } = await supabase.auth.getSession();
    let token = session?.access_token;
    
    if (!token) {
      const stored = localStorage.getItem('base360-auth-token') || localStorage.getItem('access_token');
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          token = parsed.access_token || parsed;
        } catch {
          token = stored;
        }
      }
    }

    if (!token) {
      throw new Error('No active session');
    }

    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }


  async getProfile(): Promise<ProfileResponse> {
    const response = await fetch(`${getApiBase()}/api/v1/profile`, {
      method: 'GET',
      headers: await this.getAuthHeaders()
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch profile: ${response.statusText}`);
    }

    return response.json();
  }

  async updateProfile(data: ProfileUpdateRequest): Promise<ProfileResponse['profile']> {
    const response = await fetch(`${getApiBase()}/api/v1/profile`, {
      method: 'PUT',
      headers: await this.getAuthHeaders(),
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`Failed to update profile: ${response.statusText}`);
    }

    return response.json();
  }

  async updatePreferences(data: PreferencesUpdateRequest): Promise<ProfileResponse['preferences']> {
    const response = await fetch(`${getApiBase()}/api/v1/profile/preferences`, {
      method: 'PUT',
      headers: await this.getAuthHeaders(),
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`Failed to update preferences: ${response.statusText}`);
    }

    return response.json();
  }

  async updateNotificationPreference(
    category: string, 
    data: NotificationPreferenceUpdateRequest
  ): Promise<ProfileResponse['notification_preferences'][0]> {
    const response = await fetch(`${getApiBase()}/api/v1/profile/notification-preferences/${category}`, {
      method: 'PUT',
      headers: await this.getAuthHeaders(),
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`Failed to update notification preference: ${response.statusText}`);
    }

    return response.json();
  }

  async uploadAvatar(file: File): Promise<AvatarUploadResponse> {
    try {
      const headers = await this.getAuthHeaders();
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${getApiBase()}/api/v1/profile/avatar`, {
        method: 'POST',
        headers: { Authorization: (headers)['Authorization'] as string },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status} ${response.statusText}`);
      }

      return response.json();
    } catch (error) {
      console.error('Avatar upload error:', error);
      throw error;
    }
  }

  async deleteAvatar(): Promise<{ message: string }> {
    try {
      const response = await fetch(`${getApiBase()}/api/v1/profile/avatar`, {
        method: 'DELETE',
        headers: await this.getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error(`Failed to delete avatar: ${response.statusText}`);
      }

      return response.json();
    } catch (error) {
      console.error('Avatar delete error:', error);
      throw error;
    }
  }
}

export const profileService = new ProfileService();
