import axios from 'axios';
import { supabase } from "./lib/supabase";

const backendBaseUrl = import.meta.env.VITE_BACKEND_URL
  || (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.hostname}:8000` : 'http://localhost:8000');

const Api = axios.create({
  baseURL: `${backendBaseUrl}/api/v1`,
});


  Api.interceptors.request.use(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async (config: any) => {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession();
        if (!session?.access_token) {
          throw new Error("No valid session. User must be logged in.");
        }
      const token = session.access_token;
      config.headers['Authorization'] = `Bearer ${token}`; 
    } catch (error) {
      console.error('Error fetching Cognito session:', error);
    }
    return config;
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (error: any) => {
    return Promise.reject(error);
  },
);

Api.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error)
);

export default Api;
