// src/background/background.js

import { CONFIG, MESSAGE_TYPES } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { Storage } from '../utils/storage.js';
import { AuthManager } from './auth-manager.js';
import { SyncManager } from './sync-manager.js';

// Initialize managers
const authManager = new AuthManager();
const syncManager = new SyncManager();
const SOURCE_CASE_URL_PATTERNS = [
  'https://ecourt.keralacourts.in/digicourt/Mycasesnew/mycasepet*',
  'https://ecourt.keralacourts.in/digicourt/Mycasesnew/mycaseRes*',
  'https://ecourt.keralacourts.in/digicourt/Mycasesamicus*'
];

// ============================================================================
// Extension Lifecycle
// ============================================================================

chrome.runtime.onInstalled.addListener(async (details) => {
  Logger.info('Extension installed', { reason: details.reason });
  
  await authManager.initialize();
  // Default auto-sync preference: OFF
  const existingAutoSync = await Storage.get('auto_sync');
  if (typeof existingAutoSync !== 'boolean') {
    await Storage.set('auto_sync', false);
  }
  
  // Set up periodic sync alarm (every 30 minutes)
  chrome.alarms.create('periodicSync', {
    periodInMinutes: CONFIG.SYNC_INTERVAL_MINUTES
  });
});

chrome.runtime.onStartup.addListener(async () => {
  Logger.info('Extension started');
  await authManager.initialize();
});

// ============================================================================
// Message Handler (Content Script ↔ Service Worker)
// ============================================================================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  Logger.debug('Message received', { action: request.action });
  
  // All handlers return true for async response
  
  if (request.action === MESSAGE_TYPES.VERIFY_IDENTITY) {
    handleIdentityVerification(request.data)
      .then(sendResponse)
      .catch(error => sendResponse({ verified: false, error: error.message }));
    return true;
  }
  
  if (request.action === MESSAGE_TYPES.SYNC_CASES) {
    handleCaseSync(request.data)
      .then(sendResponse)
      .catch(error => sendResponse({ status: 'error', error: error.message }));
    return true;
  }

  if (request.action === MESSAGE_TYPES.LOGIN) {
    handleLogin(request.data)
      .then(sendResponse)
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
  
  // Unknown action
  Logger.warn('Unknown message action', { action: request.action });
  sendResponse({ error: 'Unknown action' });
  return false;
});

// ============================================================================
// Handler Functions
// ============================================================================

async function handleIdentityVerification(scrapedIdentity) {
  try {
    const result = await syncManager.verifyIdentity(scrapedIdentity);
    return result;
  } catch (error) {
    Logger.error('Identity verification handler failed', { error: error.message });
    return {
      verified: false,
      error: error.message
    };
  }
}

async function handleCaseSync(payload) {
  try {
    const result = await syncManager.syncCases(payload);
    return result;
  } catch (error) {
    Logger.error('Case sync handler failed', { error: error.message });
    return {
      status: 'error',
      error: error.message
    };
  }
}

async function handleLogin(credentials) {
  const email = credentials?.email || '';
  const password = credentials?.password || '';
  return authManager.login(email, password);
}

// ============================================================================
// Alarm Handler (Periodic Sync)
// ============================================================================

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'periodicSync') {
    Logger.info('Periodic sync triggered');
    
    try {
      // Check if user is logged in
      const user = await authManager.getCurrentUser();
      if (!user) {
        Logger.debug('User not logged in, skipping periodic sync');
        return;
      }
      
      // Check user preferences
      const storedAutoSync = await Storage.get('auto_sync');
      const preferences = user.preferences || {};
      const autoSyncEnabled = typeof storedAutoSync === 'boolean'
        ? storedAutoSync
        : preferences.auto_sync === true;
      if (!autoSyncEnabled) {
        Logger.debug('Auto-sync disabled by user');
        return;
      }
      
      // Trigger sync on active KHC tab (if any)
      const tabs = await chrome.tabs.query({
        url: SOURCE_CASE_URL_PATTERNS
      });
      
      if (tabs.length > 0) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: MESSAGE_TYPES.TRIGGER_AUTO_SYNC
        }).catch(() => {
          Logger.debug('Content script not ready for auto-sync');
        });
      }
      
    } catch (error) {
      Logger.error('Periodic sync failed', { error: error.message });
    }
  }
});

// ============================================================================
// Context Menu (Right-click Actions)
// ============================================================================

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'syncCase',
    title: 'Sync this case to Lawmate',
    contexts: ['selection'],
    documentUrlPatterns: SOURCE_CASE_URL_PATTERNS
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'syncCase') {
    Logger.info('Context menu sync triggered');
    
    chrome.tabs.sendMessage(tab.id, {
      action: MESSAGE_TYPES.SYNC_SELECTED_CASE,
      selectedText: info.selectionText
    }).catch(error => {
      Logger.error('Context menu action failed', { error: error.message });
    });
  }
});

// ============================================================================
// Global Error Handler
// ============================================================================

self.addEventListener('error', (event) => {
  Logger.error('Unhandled error in service worker', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno
  });
});

self.addEventListener('unhandledrejection', (event) => {
  Logger.error('Unhandled promise rejection', {
    reason: event.reason
  });
});

Logger.info('Lawmate Service Worker loaded successfully');
