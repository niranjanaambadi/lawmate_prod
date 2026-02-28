// src/background/auth-manager.js

import { CONFIG } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { Storage } from '../utils/storage.js';
import { APIClient, APIError } from './api-client.js';

export class AuthManager {
  constructor() {
    this.apiClient = new APIClient();
    this.refreshPromise = null;
  }
  
  /**
   * Initialize auth manager
   */
  async initialize() {
    Logger.info('AuthManager initialized');
    
    // Check if JWT exists and is valid
    const isExpired = await Storage.isJWTExpired();
    if (isExpired) {
      Logger.warn('JWT expired on initialization');
      await this.clearSession();
    }
  }
  
  /**
   * Login user
   */
  async login(email, password) {
    try {
      Logger.info('Attempting login', { email });
      
      const response = await this.apiClient.post(CONFIG.ENDPOINTS.LOGIN, {
        email,
        password
      });
      
      // Store JWT and user profile
      const expiresAt = response.expires_at || this.extractTokenExpiry(response.access_token);
      await Storage.setJWT(response.access_token, expiresAt);
      await Storage.setUserProfile(response.user);
      
      Logger.info('Login successful', { user_id: response.user.id });
      
      return {
        success: true,
        user: response.user
      };
      
    } catch (error) {
      Logger.error('Login failed', { error: error.message });
      
      if (error instanceof APIError && error.statusCode === 401) {
        return {
          success: false,
          error: 'Invalid email or password'
        };
      }
      
      return {
        success: false,
        error: CONFIG.ERRORS.NETWORK_ERROR
      };
    }
  }
  
  /**
   * Ensure user is authenticated (with auto-refresh)
   */
  async ensureAuthenticated() {
    const jwt = await Storage.getJWT();
    
    if (!jwt) {
      throw new Error('USER_NOT_LOGGED_IN');
    }
    
    // Check if token needs refresh
    const expiresAt = await Storage.get(CONFIG.JWT_EXPIRY_KEY);
    if (!expiresAt) {
      return jwt;
    }

    const now = Math.floor(Date.now() / 1000);
    const timeUntilExpiry = expiresAt - now;

    if (timeUntilExpiry <= 0) {
      await this.clearSession();
      throw new Error('SESSION_EXPIRED');
    }
    
    if (timeUntilExpiry < CONFIG.JWT_REFRESH_BUFFER) {
      if (!CONFIG.ENDPOINTS.REFRESH) {
        Logger.warn('JWT nearing expiry but refresh endpoint is disabled');
        return jwt;
      }

      Logger.info('JWT expiring soon, refreshing...', { 
        secondsRemaining: timeUntilExpiry 
      });
      
      // Prevent concurrent refresh requests
      if (!this.refreshPromise) {
        this.refreshPromise = this.refreshToken().finally(() => {
          this.refreshPromise = null;
        });
      }
      
      await this.refreshPromise;
    }
    
    return await Storage.getJWT();
  }
  
  /**
   * Refresh JWT token
   */
  async refreshToken() {
    try {
      if (!CONFIG.ENDPOINTS.REFRESH) {
        throw new Error('REFRESH_ENDPOINT_NOT_CONFIGURED');
      }

      const currentToken = await Storage.getJWT();
      
      if (!currentToken) {
        throw new Error('No token to refresh');
      }
      
      const response = await this.apiClient.post(CONFIG.ENDPOINTS.REFRESH);
      
      await Storage.setJWT(response.access_token, response.expires_at);
      
      Logger.info('JWT refreshed successfully');
      
      return response.access_token;
      
    } catch (error) {
      Logger.error('JWT refresh failed', { error: error.message });
      
      // Clear session on refresh failure
      await this.clearSession();
      
      // Notify user
      await chrome.notifications.create({
        type: 'basic',
        iconUrl: chrome.runtime.getURL('assets/icon48.png'),
        title: 'Lawmate Session Expired',
        message: 'Please log in again at lawmate.in',
        priority: 2
      });
      
      throw error;
    }
  }
  
  /**
   * Clear user session (security wipe)
   */
  async clearSession() {
    Logger.warn('Clearing user session');
    await Storage.clear();
  }
  
  /**
   * Get current user profile
   */
  async getCurrentUser() {
    return await Storage.getUserProfile();
  }

  /**
   * Extract JWT expiry (`exp`) as unix seconds.
   */
  extractTokenExpiry(token) {
    try {
      const payloadBase64 = token.split('.')[1];
      if (!payloadBase64) return null;

      const payloadJson = atob(payloadBase64.replace(/-/g, '+').replace(/_/g, '/'));
      const payload = JSON.parse(payloadJson);
      return typeof payload.exp === 'number' ? payload.exp : null;
    } catch (error) {
      Logger.warn('Could not extract token expiry', { error: error.message });
      return null;
    }
  }
}
