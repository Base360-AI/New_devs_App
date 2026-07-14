import React, { useState, useEffect } from 'react';
import { 
  Save, User, Settings, Bell, Palette, RefreshCw, Eye, Layout,
  MapPin, Briefcase, Phone, Mail, Clock, Languages, Monitor, AlertCircle,
  X, Camera, Edit3, Shield, Smartphone, Volume
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { profileService } from '../../services/profileService';
import { ProfileResponse, ProfileUpdateRequest, PreferencesUpdateRequest } from '../../types/profile';
import AvatarUpload from './AvatarUpload';
import { useAuth } from '../../contexts/AuthContext.new';

const ProfilePage: React.FC = () => {
  const { user, loading: authLoading } = useAuth();
  const [profileData, setProfileData] = useState<ProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<'profile' | 'preferences' | 'notifications'>('profile');
  const [hasChanges, setHasChanges] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [profileForm, setProfileForm] = useState<ProfileUpdateRequest>({});
  const [preferencesForm, setPreferencesForm] = useState<PreferencesUpdateRequest>({});

  useEffect(() => {
    if (authLoading) {
      return;
    }

    if (!user) {
      setLoading(false);
      setProfileData(null);
      setError('Please sign in to view your profile');
      return;
    }

    loadProfile();
  }, [user, authLoading]);

  useEffect(() => {
    if (!profileData) return;
    
    const profileChanged = Object.keys(profileForm).some(key => {
      const typedKey = key as keyof ProfileUpdateRequest;
      return profileForm[typedKey] !== profileData.profile[typedKey];
    });
    
    const preferencesChanged = Object.keys(preferencesForm).some(key => {
      const typedKey = key as keyof PreferencesUpdateRequest;
      return preferencesForm[typedKey] !== profileData.preferences[typedKey];
    });
    
    setHasChanges(profileChanged || preferencesChanged);
  }, [profileForm, preferencesForm, profileData]);

  const loadProfile = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await profileService.getProfile();
      setProfileData(data);
      
      // Initialize forms with current data
      setProfileForm({
        display_name: data.profile.display_name || '',
        bio: data.profile.bio || '',
        phone: data.profile.phone || '',
        department: data.profile.department || '',
        job_title: data.profile.job_title || '',
        location: data.profile.location || '',
        timezone: data.profile.timezone,
        language: data.profile.language,
        theme: data.profile.theme
      });
      
      setPreferencesForm({
        notification_email: data.preferences.notification_email,
        notification_push: data.preferences.notification_push,
        notification_desktop: data.preferences.notification_desktop,
        notification_sound: data.preferences.notification_sound,
        auto_refresh: data.preferences.auto_refresh,
        compact_view: data.preferences.compact_view,
        sidebar_collapsed: data.preferences.sidebar_collapsed
      });
      
    } catch (error) {
      console.error('Error loading profile:', error);
      setError('Failed to load profile data');
      toast.error('Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  const handleProfileSave = async () => {
    if (!profileData) return;
    
    setSaving(true);
    try {
      setError(null);
      // Only send changed fields
      const changes: ProfileUpdateRequest = {};
      Object.keys(profileForm).forEach(key => {
        const typedKey = key as keyof ProfileUpdateRequest;
        if (profileForm[typedKey] !== profileData.profile[typedKey]) {
          changes[typedKey] = profileForm[typedKey];
        }
      });

      if (Object.keys(changes).length === 0) {
        toast.success('No changes to save');
        return;
      }

      const updatedProfile = await profileService.updateProfile(changes);
      setProfileData(prev => prev ? { ...prev, profile: updatedProfile } : null);
      toast.success('Profile updated successfully!');
    } catch (error) {
      console.error('Error updating profile:', error);
      setError('Failed to update profile');
      toast.error('Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handlePreferencesSave = async () => {
    if (!profileData) return;
    
    setSaving(true);
    try {
      setError(null);
      // Only send changed fields
      const changes: PreferencesUpdateRequest = {};
      Object.keys(preferencesForm).forEach(key => {
        const typedKey = key as keyof PreferencesUpdateRequest;
        if (preferencesForm[typedKey] !== profileData.preferences[typedKey]) {
          changes[typedKey] = preferencesForm[typedKey];
        }
      });

      if (Object.keys(changes).length === 0) {
        toast.success('No changes to save');
        return;
      }

      const updatedPreferences = await profileService.updatePreferences(changes);
      setProfileData(prev => prev ? { ...prev, preferences: updatedPreferences } : null);
      toast.success('Preferences updated successfully!');
    } catch (error) {
      console.error('Error updating preferences:', error);
      setError('Failed to update preferences');
      toast.error('Failed to update preferences');
    } finally {
      setSaving(false);
    }
  };

  const handleNotificationPreferenceChange = async (category: string, field: string, value: boolean) => {
    try {
      await profileService.updateNotificationPreference(category, { [field]: value });
      
      // Update local state
      setProfileData(prev => {
        if (!prev) return null;
        
        const updatedPrefs = prev.notification_preferences.map(pref => 
          pref.category === category 
            ? { ...pref, [field]: value }
            : pref
        );
        
        return { ...prev, notification_preferences: updatedPrefs };
      });
      
      toast.success('Notification preference updated');
    } catch (error) {
      console.error('Error updating notification preference:', error);
      toast.error('Failed to update notification preference');
    }
  };

  const handleAvatarUpdate = (url: string | null) => {
    setProfileData(prev => prev ? {
      ...prev,
      profile: { ...prev.profile, avatar_url: url }
    } : null);
  };

  const handleReset = () => {
    if (!profileData) return;
    
    setProfileForm({
      display_name: profileData.profile.display_name || '',
      bio: profileData.profile.bio || '',
      phone: profileData.profile.phone || '',
      department: profileData.profile.department || '',
      job_title: profileData.profile.job_title || '',
      location: profileData.profile.location || '',
      timezone: profileData.profile.timezone,
      language: profileData.profile.language,
      theme: profileData.profile.theme
    });
    
    setPreferencesForm({
      notification_email: profileData.preferences.notification_email,
      notification_push: profileData.preferences.notification_push,
      notification_desktop: profileData.preferences.notification_desktop,
      notification_sound: profileData.preferences.notification_sound,
      auto_refresh: profileData.preferences.auto_refresh,
      compact_view: profileData.preferences.compact_view,
      sidebar_collapsed: profileData.preferences.sidebar_collapsed
    });
    
    setError(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex items-center gap-3 text-gray-500">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
          <span className="text-sm font-medium">Loading profile...</span>
        </div>
      </div>
    );
  }

  if (!profileData) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Failed to Load Profile</h2>
          <p className="text-gray-600 mb-4">There was an error loading your profile data.</p>
          <button
            onClick={loadProfile}
            className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User, description: 'Personal information and settings' },
    { id: 'preferences', label: 'Preferences', icon: Settings, description: 'App preferences and display options' },
    { id: 'notifications', label: 'Notifications', icon: Bell, description: 'Notification settings by category' }
  ] as const;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {/* Header with Profile Summary */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-8 overflow-hidden">
          <div className="bg-gradient-to-r from-primary/10 to-primary/5 px-8 py-6">
            <div className="flex items-center gap-6">
              <div className="relative">
                <div className="w-20 h-20 rounded-full overflow-hidden bg-gray-100 border-4 border-white shadow-lg">
                  {profileData.profile.avatar_url ? (
                    <img
                      src={profileData.profile.avatar_url}
                      alt="Profile"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <User className="w-8 h-8 text-gray-400" />
                    </div>
                  )}
                </div>
              </div>
              <div className="flex-1">
                <h1 className="text-2xl font-bold text-gray-900">
                  {profileData.profile.display_name || 'User Profile'}
                </h1>
                <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                  {profileData.profile.job_title && (
                    <span className="flex items-center gap-1">
                      <Briefcase className="w-4 h-4" />
                      {profileData.profile.job_title}
                    </span>
                  )}
                  {profileData.profile.department && (
                    <span className="flex items-center gap-1">
                      <Shield className="w-4 h-4" />
                      {profileData.profile.department}
                    </span>
                  )}
                  {profileData.profile.location && (
                    <span className="flex items-center gap-1">
                      <MapPin className="w-4 h-4" />
                      {profileData.profile.location}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="border-b border-gray-200">
            <nav className="flex" role="tablist">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    role="tab"
                    aria-selected={activeTab === tab.id}
                    className={`flex-1 flex flex-col items-center px-6 py-4 text-sm font-medium border-b-2 transition-all duration-200 ${
                      activeTab === tab.id
                        ? 'border-primary text-primary bg-primary/5'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <Icon className="w-5 h-5 mb-1" />
                    <span className="font-semibold">{tab.label}</span>
                    <span className="text-xs text-gray-500 mt-1 hidden sm:block">{tab.description}</span>
                  </button>
                );
              })}
            </nav>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="text-red-800 text-sm font-medium">{error}</span>
            </div>
            <button 
              onClick={() => setError(null)} 
              className="text-red-600 hover:text-red-800 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Content */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100">
          <div className="p-8">
            {activeTab === 'profile' && (
              <div className="space-y-8">
                {/* Avatar Upload Section */}
                <div className="text-center">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center justify-center gap-2">
                    <Camera className="w-5 h-5" />
                    Profile Picture
                  </h3>
                  <AvatarUpload
                    currentAvatarUrl={profileData.profile.avatar_url}
                    onAvatarUpdate={handleAvatarUpdate}
                    size="lg"
                  />
                </div>

                {/* Basic Information */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
                    <Edit3 className="w-5 h-5" />
                    Basic Information
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label htmlFor="display-name" className="block text-sm font-semibold text-gray-700 mb-2">
                        Display Name
                      </label>
                      <input
                        id="display-name"
                        type="text"
                        value={profileForm.display_name || ''}
                        onChange={(e) => setProfileForm(prev => ({ ...prev, display_name: e.target.value }))}
                        className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                        placeholder="Your display name"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Phone Number
                      </label>
                      <div className="relative">
                        <Phone className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <input
                          type="tel"
                          value={profileForm.phone || ''}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, phone: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                          placeholder="+1 (555) 000-0000"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Job Title
                      </label>
                      <div className="relative">
                        <Briefcase className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <input
                          type="text"
                          value={profileForm.job_title || ''}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, job_title: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                          placeholder="Software Engineer"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Department
                      </label>
                      <div className="relative">
                        <Shield className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <input
                          type="text"
                          value={profileForm.department || ''}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, department: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                          placeholder="Engineering"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Location
                      </label>
                      <div className="relative">
                        <MapPin className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <input
                          type="text"
                          value={profileForm.location || ''}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, location: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                          placeholder="London, UK"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Timezone
                      </label>
                      <div className="relative">
                        <Clock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <select
                          value={profileForm.timezone || 'UTC'}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, timezone: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                        >
                          <option value="UTC">UTC</option>
                          <option value="Europe/London">London (GMT)</option>
                          <option value="Europe/Paris">Paris (CET)</option>
                          <option value="Africa/Algiers">Algiers (CET)</option>
                          <option value="Europe/Lisbon">Lisbon (WET)</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  <div className="mt-6">
                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                      Bio
                    </label>
                    <textarea
                      value={profileForm.bio || ''}
                      onChange={(e) => setProfileForm(prev => ({ ...prev, bio: e.target.value }))}
                      rows={4}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                      placeholder="Tell us about yourself..."
                    />
                  </div>
                </div>

                {/* App Settings */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
                    <Palette className="w-5 h-5" />
                    App Settings
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Language
                      </label>
                      <div className="relative">
                        <Languages className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <select
                          value={profileForm.language || 'en'}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, language: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                        >
                          <option value="en">English</option>
                          <option value="fr">Français</option>
                          <option value="ar">العربية</option>
                          <option value="es">Español</option>
                          <option value="pt">Português</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-semibold text-gray-700 mb-2">
                        Theme
                      </label>
                      <div className="relative">
                        <Monitor className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <select
                          value={profileForm.theme || 'light'}
                          onChange={(e) => setProfileForm(prev => ({ ...prev, theme: e.target.value }))}
                          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                        >
                          <option value="light">Light</option>
                          <option value="dark">Dark</option>
                          <option value="auto">Auto</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center justify-between pt-6 border-t border-gray-200">
                  <button
                    onClick={handleReset}
                    disabled={!hasChanges || saving}
                    className="px-4 py-2 text-gray-600 hover:text-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 text-sm font-medium"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Reset Changes
                  </button>

                  <div className="flex items-center gap-3">
                    {hasChanges && (
                      <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded font-medium">
                        Unsaved changes
                      </span>
                    )}
                    <button
                      onClick={handleProfileSave}
                      disabled={!hasChanges || saving}
                      className="px-6 py-2.5 bg-primary text-white rounded-lg hover:bg-primary-dark focus:ring-2 focus:ring-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center gap-2 font-medium text-sm shadow-sm"
                    >
                      {saving ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="h-4 w-4" />
                          Save Changes
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'preferences' && (
              <div className="space-y-8">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
                    <Settings className="w-5 h-5" />
                    General Preferences
                  </h3>
                  
                  <div className="space-y-6">
                    <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-100 rounded-lg">
                          <RefreshCw className="w-5 h-5 text-blue-600" />
                        </div>
                        <div>
                          <label className="text-sm font-semibold text-gray-900">Auto Refresh</label>
                          <p className="text-sm text-gray-500">Automatically refresh data in real-time</p>
                        </div>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={preferencesForm.auto_refresh || false}
                          onChange={(e) => setPreferencesForm(prev => ({ ...prev, auto_refresh: e.target.checked }))}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                      </label>
                    </div>

                    <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-green-100 rounded-lg">
                          <Eye className="w-5 h-5 text-green-600" />
                        </div>
                        <div>
                          <label className="text-sm font-semibold text-gray-900">Compact View</label>
                          <p className="text-sm text-gray-500">Use compact layout for lists and tables</p>
                        </div>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={preferencesForm.compact_view || false}
                          onChange={(e) => setPreferencesForm(prev => ({ ...prev, compact_view: e.target.checked }))}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                      </label>
                    </div>

                    <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-purple-100 rounded-lg">
                          <Layout className="w-5 h-5 text-purple-600" />
                        </div>
                        <div>
                          <label className="text-sm font-semibold text-gray-900">Collapsed Sidebar</label>
                          <p className="text-sm text-gray-500">Keep sidebar collapsed by default</p>
                        </div>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={preferencesForm.sidebar_collapsed || false}
                          onChange={(e) => setPreferencesForm(prev => ({ ...prev, sidebar_collapsed: e.target.checked }))}
                          className="sr-only peer"
                        />
                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                      </label>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex justify-end pt-6 border-t border-gray-200">
                  <button
                    onClick={handlePreferencesSave}
                    disabled={!hasChanges || saving}
                    className="px-6 py-2.5 bg-primary text-white rounded-lg hover:bg-primary-dark focus:ring-2 focus:ring-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center gap-2 font-medium text-sm shadow-sm"
                  >
                    {saving ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        Saving...
                      </>
                    ) : (
                      <>
                        <Save className="h-4 w-4" />
                        Save Preferences
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'notifications' && (
              <div className="space-y-8">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
                    <Bell className="w-5 h-5" />
                    Notification Settings
                  </h3>
                  
                  <div className="space-y-6">
                    {profileData.notification_preferences.map((pref) => (
                      <div key={pref.category} className="border border-gray-200 rounded-lg p-6 bg-gray-50">
                        <h4 className="text-base font-semibold text-gray-900 mb-4 capitalize flex items-center gap-2">
                          <Bell className="w-4 h-4" />
                          {pref.category} Notifications
                        </h4>
                        
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2">
                              <Mail className="w-4 h-4 text-gray-500" />
                              <span className="text-sm font-medium text-gray-700">Email</span>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={pref.email_enabled}
                                onChange={(e) => handleNotificationPreferenceChange(pref.category, 'email_enabled', e.target.checked)}
                                className="sr-only peer"
                              />
                              <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                            </label>
                          </div>

                          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2">
                              <Smartphone className="w-4 h-4 text-gray-500" />
                              <span className="text-sm font-medium text-gray-700">Push</span>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={pref.push_enabled}
                                onChange={(e) => handleNotificationPreferenceChange(pref.category, 'push_enabled', e.target.checked)}
                                className="sr-only peer"
                              />
                              <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                            </label>
                          </div>

                          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2">
                              <Monitor className="w-4 h-4 text-gray-500" />
                              <span className="text-sm font-medium text-gray-700">Desktop</span>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={pref.desktop_enabled}
                                onChange={(e) => handleNotificationPreferenceChange(pref.category, 'desktop_enabled', e.target.checked)}
                                className="sr-only peer"
                              />
                              <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                            </label>
                          </div>

                          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
                            <div className="flex items-center gap-2">
                              <Volume className="w-4 h-4 text-gray-500" />
                              <span className="text-sm font-medium text-gray-700">Sound</span>
                            </div>
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={pref.sound_enabled}
                                onChange={(e) => handleNotificationPreferenceChange(pref.category, 'sound_enabled', e.target.checked)}
                                className="sr-only peer"
                              />
                              <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                            </label>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;