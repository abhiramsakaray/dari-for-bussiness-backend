// src/services/auth.ts
import api from './api';

export interface LoginResponse {
  access_token: string;
  token_type: string;
  api_key: string;  // Automatically provided
}

export const authService = {
  /**
   * Register a new merchant account
   * Automatically receives API key in response
   */
  register: async (name: string, email: string, password: string) => {
    const response = await api.post<LoginResponse>('/auth/register', {
      name,
      email,
      password,
    });
    
    // Automatically store both token and API key
    localStorage.setItem('merchant_token', response.data.access_token);
    localStorage.setItem('merchant_api_key', response.data.api_key);
    
    return response.data;
  },

  /**
   * Login to merchant account
   * Automatically receives API key in response
   */
  login: async (email: string, password: string) => {
    const response = await api.post<LoginResponse>('/auth/login', {
      email,
      password,
    });
    
    // Automatically store both token and API key
    localStorage.setItem('merchant_token', response.data.access_token);
    localStorage.setItem('merchant_api_key', response.data.api_key);
    
    return response.data;
  },

  /**
   * Logout - clear all stored credentials
   */
  logout: () => {
    localStorage.removeItem('merchant_token');
    localStorage.removeItem('merchant_api_key');
    window.location.href = '/login';
  },

  /**
   * Check if user is authenticated
   */
  isAuthenticated: () => {
    return !!(localStorage.getItem('merchant_token') && localStorage.getItem('merchant_api_key'));
  },

  /**
   * Get current API key
   */
  getApiKey: () => {
    return localStorage.getItem('merchant_api_key');
  },
};
