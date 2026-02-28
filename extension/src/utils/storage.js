// src/utils/storage.js

import { CONFIG } from './constants.js';

export class Storage {
  /**
   * Get item from chrome.storage.local
   */
  static async get(key) {
    try {
      const result = await chrome.storage.local.get(key);
      return result[key];
    } catch (error) {
      console.error(`Storage.get error for key ${key}:`, error);
      return null;
    }
  }
  
  /**
   * Set item in chrome.storage.local
   */
  static async set(key, value) {
    try {
      await chrome.storage.local.set({ [key]: value });
      return true;
    } catch (error) {
      console.error(`Storage.set error for key ${key}:`, error);
      return false;
    }
  }
  
  /**
   * Remove item from chrome.storage.local
   */
  static async remove(key) {
    try {
      await chrome.storage.local.remove(key);
      return true;
    } catch (error) {
      console.error(`Storage.remove error for key ${key}:`, error);
      return false;
    }
  }
  
  /**
   * Clear all storage (security wipe)
   */
  static async clear() {
    try {
      await chrome.storage.local.clear();
      console.log('Storage cleared successfully');
      return true;
    } catch (error) {
      console.error('Storage.clear error:', error);
      return false;
    }
  }
  
  /**
   * Get JWT token
   */
  static async getJWT() {
    return await this.get(CONFIG.JWT_STORAGE_KEY);
  }
  
  /**
   * Set JWT token with expiry
   */
  static async setJWT(token, expiresAt) {
    await this.set(CONFIG.JWT_STORAGE_KEY, token);
    await this.set(CONFIG.JWT_EXPIRY_KEY, expiresAt);
  }
  
  /**
   * Check if JWT is expired
   */
  static async isJWTExpired() {
    const expiresAt = await this.get(CONFIG.JWT_EXPIRY_KEY);
    if (!expiresAt) return true;
    
    const now = Math.floor(Date.now() / 1000);
    return now >= expiresAt;
  }
  
  /**
   * Get user profile
   */
  static async getUserProfile() {
    return await this.get(CONFIG.STORAGE_KEYS.USER_PROFILE);
  }
  
  /**
   * Set user profile
   */
  static async setUserProfile(profile) {
    return await this.set(CONFIG.STORAGE_KEYS.USER_PROFILE, profile);
  }
}