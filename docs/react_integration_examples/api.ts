// src/services/api.ts
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Create axios instance
export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add authentication headers to all requests
api.interceptors.request.use((config) => {
  // Add JWT token for merchant-specific endpoints
  const token = localStorage.getItem('merchant_token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  
  // Add API key for payment session creation
  const apiKey = localStorage.getItem('merchant_api_key');
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  
  return config;
});

// Handle errors globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid - clear storage and redirect to login
      localStorage.removeItem('merchant_token');
      localStorage.removeItem('merchant_api_key');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
