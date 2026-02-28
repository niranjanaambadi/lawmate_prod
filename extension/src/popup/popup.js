// src/popup/popup.js

import { CONFIG, MESSAGE_TYPES } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { Storage } from '../utils/storage.js';

class LawmatePopup {
  constructor() {
    this.user = null;
    this.initializeElements();
    this.attachEventListeners();
    this.loadUserData();
  }
  
  /**
   * Initialize DOM element references
   */
  initializeElements() {
    // Views
    this.loggedInView = document.getElementById('loggedInView');
    this.loggedOutView = document.getElementById('loggedOutView');
    this.actionsSection = document.getElementById('actionsSection');
    
    // User info
    this.userInitials = document.getElementById('userInitials');
    this.userName = document.getElementById('userName');
    this.userKhcId = document.getElementById('userKhcId');
    this.lastSync = document.getElementById('lastSync');
    this.caseCount = document.getElementById('caseCount');
    
    // Buttons
    this.loginButton = document.getElementById('loginButton');
    this.loginForm = document.getElementById('loginForm');
    this.loginEmail = document.getElementById('loginEmail');
    this.loginPassword = document.getElementById('loginPassword');
    this.syncNowButton = document.getElementById('syncNowButton');
    this.openDashboardButton = document.getElementById('openDashboardButton');
    this.logoutButton = document.getElementById('logoutButton');
    this.clearCacheButton = document.getElementById('clearCacheButton');
    
    // Settings
    this.autoSyncToggle = document.getElementById('autoSyncToggle');
    
    // Loading
    this.loadingOverlay = document.getElementById('loadingOverlay');
    this.loadingText = document.getElementById('loadingText');
  }
  
  /**
   * Attach event listeners
   */
  attachEventListeners() {
    this.loginForm?.addEventListener('submit', (e) => this.handleLogin(e));
    this.syncNowButton?.addEventListener('click', () => this.handleSyncNow());
    this.openDashboardButton?.addEventListener('click', () => this.handleOpenDashboard());
    this.logoutButton?.addEventListener('click', () => this.handleLogout());
    this.clearCacheButton?.addEventListener('click', () => this.handleClearCache());
    this.autoSyncToggle?.addEventListener('change', (e) => this.handleAutoSyncToggle(e));
  }
  
  /**
   * Load user data from storage
   */
  async loadUserData() {
    try {
      this.showLoading('Loading...');
      
      // Get user profile from storage
      this.user = await Storage.getUserProfile();
      
      if (this.user) {
        await this.renderLoggedInView();
      } else {
        this.renderLoggedOutView();
      }
      
    } catch (error) {
      Logger.error('Failed to load user data', { error: error.message });
      this.showError('Failed to load user data');
    } finally {
      this.hideLoading();
    }
  }
  
  /**
   * Render logged-in view
   */
  async renderLoggedInView() {
    // Show logged-in view
    this.loggedInView.classList.remove('hidden');
    this.loggedOutView.classList.add('hidden');
    this.actionsSection.classList.remove('hidden');
    this.logoutButton.classList.remove('hidden');
    
    // Set user info
    this.userName.textContent = this.user.khc_advocate_name || 'Unknown Advocate';
    this.userKhcId.textContent = this.user.khc_advocate_id || 'N/A';
    
    // Set initials
    const initials = this.getInitials(this.user.khc_advocate_name);
    this.userInitials.textContent = initials;
    
    // Load sync status
    await this.loadSyncStatus();
    
    // Load auto-sync preference
    const preferences = this.user.preferences || {};
    const storedAutoSync = await Storage.get('auto_sync');
    // Default OFF unless user has explicitly enabled it.
    this.autoSyncToggle.checked = typeof storedAutoSync === 'boolean'
      ? storedAutoSync
      : preferences.auto_sync === true;
  }
  
  /**
   * Render logged-out view
   */
  renderLoggedOutView() {
    this.loggedInView.classList.add('hidden');
    this.loggedOutView.classList.remove('hidden');
    this.actionsSection.classList.add('hidden');
    this.logoutButton.classList.add('hidden');
  }
  
  /**
   * Load sync status
   */
  async loadSyncStatus() {
    try {
      // Get last sync timestamp
      const lastSyncTimestamp = await Storage.get(CONFIG.STORAGE_KEYS.LAST_SYNC);
      
      if (lastSyncTimestamp) {
        const lastSyncDate = new Date(lastSyncTimestamp);
        this.lastSync.textContent = this.formatRelativeTime(lastSyncDate);
      } else {
        this.lastSync.textContent = 'Never';
      }
      
      // Get case count from backend
      const caseCount = await this.fetchCaseCount();
      this.caseCount.textContent = caseCount.toString();
      
    } catch (error) {
      Logger.error('Failed to load sync status', { error: error.message });
    }
  }
  
  /**
   * Fetch case count from backend
   */
  async fetchCaseCount() {
    try {
      const jwt = await Storage.getJWT();
      if (!jwt) return 0;
      
      const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1/cases?page=1&per_page=1`, {
        headers: {
          'Authorization': `Bearer ${jwt}`
        }
      });
      
      if (!response.ok) return 0;
      
      const data = await response.json();
      return data.total || 0;
      
    } catch (error) {
      Logger.error('Failed to fetch case count', { error: error.message });
      return 0;
    }
  }
  
  /**
   * Handle login button click
   */
  async handleLogin(event) {
    event?.preventDefault();

    const email = this.loginEmail?.value?.trim();
    const password = this.loginPassword?.value || '';

    if (!email || !password) {
      this.showError('Please enter email and password.');
      return;
    }

    try {
      this.showLoading('Signing in...');

      const response = await new Promise((resolve) => {
        chrome.runtime.sendMessage({
          action: MESSAGE_TYPES.LOGIN,
          data: { email, password }
        }, resolve);
      });

      if (chrome.runtime.lastError) {
        throw new Error(chrome.runtime.lastError.message);
      }

      if (!response?.success) {
        throw new Error(response?.error || 'Login failed');
      }

      // Reset form and re-render from storage
      if (this.loginForm) this.loginForm.reset();
      await this.loadUserData();
      this.showSuccess('Logged in successfully');
    } catch (error) {
      Logger.error('Extension login failed', { error: error.message });
      this.showError(error.message || 'Login failed');
    } finally {
      this.hideLoading();
    }
  }

  handleWebSignIn() {
    chrome.tabs.create({
      url: `${CONFIG.WEB_BASE_URL}/signin`
    });
  }
  
  /**
   * Handle sync now button click
   */
  async handleSyncNow() {
    try {
      this.showLoading('Syncing cases...');

      // Prefer current active tab to avoid sending to a stale matching tab.
      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const activeUrl = activeTab?.url || '';
      const isActiveSourceTab = this.isKHCMyCasesUrl(activeUrl);

      let targetTab = null;
      if (isActiveSourceTab) {
        targetTab = activeTab;
      } else {
        const tabs = await chrome.tabs.query({
          url: [
            'https://ecourt.keralacourts.in/digicourt/Mycasesnew/mycasepet*',
            'https://ecourt.keralacourts.in/digicourt/Mycasesnew/mycaseRes*',
            'https://ecourt.keralacourts.in/digicourt/Mycasesamicus*'
          ]
        });
        targetTab = tabs[0] || null;
      }

      if (!targetTab?.id) {
        this.showError('Please open the DigiCourt "My Cases" page first');
        return;
      }

      // Send sync trigger to content script
      await chrome.tabs.sendMessage(targetTab.id, {
        action: MESSAGE_TYPES.TRIGGER_AUTO_SYNC
      });
      
      this.showSuccess('Sync started! Check the KHC page for progress.');
      
      // Refresh sync status after 5 seconds
      setTimeout(() => this.loadSyncStatus(), 5000);
      
    } catch (error) {
      Logger.error('Sync now failed', { error: error.message });
      if (String(error?.message || '').includes('Receiving end does not exist')) {
        this.showError('KHC tab is open, but extension script is not loaded. Refresh the KHC page and try again.');
      } else {
        this.showError('Failed to start sync. Make sure you are on the KHC portal.');
      }
    } finally {
      this.hideLoading();
    }
  }

  isKHCMyCasesUrl(url) {
    if (!url) return false;
    return (
      url.startsWith('https://ecourt.keralacourts.in/digicourt/Mycasesnew/mycasepet') ||
      url.startsWith('https://ecourt.keralacourts.in/digicourt/Mycasesnew/mycaseRes') ||
      url.startsWith('https://ecourt.keralacourts.in/digicourt/Mycasesamicus')
    );
  }
  
  /**
   * Handle open dashboard button click
   */
  handleOpenDashboard() {
    chrome.tabs.create({
      url: `${CONFIG.WEB_BASE_URL}/dashboard`
    });
  }
  
  /**
   * Handle logout button click
   */
  async handleLogout() {
    const confirmed = confirm('Are you sure you want to logout? All synced data will remain safe in your Lawmate account.');
    
    if (!confirmed) return;
    
    try {
      this.showLoading('Logging out...');
      
      // Clear storage
      await Storage.clear();
      
      // Reload popup
      this.user = null;
      this.renderLoggedOutView();
      
      this.showSuccess('Logged out successfully');
      
    } catch (error) {
      Logger.error('Logout failed', { error: error.message });
      this.showError('Failed to logout');
    } finally {
      this.hideLoading();
    }
  }
  
  /**
   * Handle clear cache button click
   */
  async handleClearCache() {
    const confirmed = confirm('This will clear temporary sync data from your browser. Your cases remain safe on Lawmate servers.');
    
    if (!confirmed) return;
    
    try {
      this.showLoading('Clearing cache...');
      
      // Clear only cache-related keys, not JWT
      await Storage.remove(CONFIG.STORAGE_KEYS.LAST_SYNC);
      await Storage.remove(CONFIG.STORAGE_KEYS.SYNC_STATUS);
      await Storage.remove(CONFIG.STORAGE_KEYS.UPLOAD_QUEUE);
      
      this.showSuccess('Cache cleared successfully');
      
      await this.loadSyncStatus();
      
    } catch (error) {
      Logger.error('Clear cache failed', { error: error.message });
      this.showError('Failed to clear cache');
    } finally {
      this.hideLoading();
    }
  }
  
  /**
   * Handle auto-sync toggle
   */
  async handleAutoSyncToggle(event) {
    const enabled = event.target.checked;
    
    try {
      // Update user preferences
      if (this.user) {
        this.user.preferences = {
          ...this.user.preferences,
          auto_sync: enabled
        };
        
        await Storage.setUserProfile(this.user);
        await Storage.set('auto_sync', enabled);
        
        Logger.info('Auto-sync preference updated', { enabled });
      }
      
    } catch (error) {
      Logger.error('Failed to update auto-sync preference', { error: error.message });
      // Revert toggle
      event.target.checked = !enabled;
    }
  }
  
  /**
   * Show loading overlay
   */
  showLoading(text = 'Loading...') {
    this.loadingText.textContent = text;
    this.loadingOverlay.classList.remove('hidden');
  }
  
  /**
   * Hide loading overlay
   */
  hideLoading() {
    this.loadingOverlay.classList.add('hidden');
  }
  
  /**
   * Show error notification
   */
  showError(message) {
    this.showNotification(message, 'error');
  }
  
  /**
   * Show success notification
   */
  showSuccess(message) {
    this.showNotification(message, 'success');
  }
  
  /**
   * Show notification (simple alert for now, can be enhanced)
   */
  showNotification(message, type = 'info') {
    // For now, use alert
    // TODO: Implement custom notification UI
    alert(message);
  }
  
  /**
   * Get initials from name
   */
  getInitials(name) {
    if (!name) return 'LA';
    
    const words = name.trim().split(' ');
    if (words.length === 1) {
      return words[0].substring(0, 2).toUpperCase();
    }
    
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  }
  
  /**
   * Format relative time
   */
  formatRelativeTime(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    
    return date.toLocaleDateString();
  }
}

// Initialize popup
document.addEventListener('DOMContentLoaded', () => {
  new LawmatePopup();
});
