// extension/src/content/content.js

/**
 * Lawmate Content Script
 * 
 * This script runs on the Kerala High Court E-Filing portal's "My Cases" page.
 * It extracts case metadata, handles identity verification, and orchestrates
 * the sync process with the Lawmate backend.
 * 
 * Version: 1.1.0
 * Last Updated: 2026-01-15
 */

import { CONFIG, MESSAGE_TYPES, SYNC_STATUS, UPLOAD_STATUS } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { KHCDOMParser } from './dom-parser.js';

// ============================================================================
// UI Manager - Inject Lawmate sync indicators
// ============================================================================

class LawmateUI {
  constructor() {
    this.statusMap = new Map();
    this.syncButton = null;
    this.notificationQueue = [];
  }
  
  /**
   * Initialize UI components
   */
  initialize() {
    this.injectStyles();
    this.injectSyncColumn();
    this.injectSyncButton();
    this.injectNotificationContainer();
    this.attachEventListeners();
  }
  
  /**
   * Inject custom CSS styles
   */
  injectStyles() {
    if (document.getElementById('lawmate-styles')) return;
    
    const style = document.createElement('style');
    style.id = 'lawmate-styles';
    style.textContent = `
      /* Lawmate Status Cell */
      .lawmate-status-cell {
        min-width: 140px;
        padding: 8px !important;
        vertical-align: middle;
      }
      
      .lawmate-sync-status {
        display: flex;
        align-items: center;
        gap: 8px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 13px;
        font-weight: 500;
        padding: 6px 12px;
        border-radius: 6px;
        background: #f8f9fa;
        transition: all 0.3s ease;
      }
      
      .lawmate-sync-status.status-pending {
        background: #fff3cd;
        color: #856404;
      }
      
      .lawmate-sync-status.status-syncing {
        background: #d1ecf1;
        color: #0c5460;
      }
      
      .lawmate-sync-status.status-uploading {
        background: #e7f3ff;
        color: #004085;
      }
      
      .lawmate-sync-status.status-success {
        background: #d4edda;
        color: #155724;
      }
      
      .lawmate-sync-status.status-failed {
        background: #f8d7da;
        color: #721c24;
      }
      
      .status-icon {
        font-size: 16px;
        line-height: 1;
      }
      
      .status-text {
        flex: 1;
        white-space: nowrap;
      }
      
      /* Animated spinner */
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      
      .status-icon.spinning {
        animation: spin 1s linear infinite;
      }
      
      /* Progress bar */
      .upload-progress {
        width: 100%;
        height: 4px;
        background: #e9ecef;
        border-radius: 2px;
        margin-top: 4px;
        overflow: hidden;
      }
      
      .upload-progress-bar {
        height: 100%;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        transition: width 0.3s ease;
      }
      
      /* Sync Button */
      #lawmate-sync-button {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 9999;
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 24px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        font-size: 15px;
        font-weight: 600;
        cursor: pointer;
        box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      }
      
      #lawmate-sync-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 28px rgba(102, 126, 234, 0.4);
      }
      
      #lawmate-sync-button:active {
        transform: translateY(0);
      }
      
      #lawmate-sync-button.syncing {
        background: linear-gradient(135deg, #4a5fe6 0%, #5a3d8a 100%);
        cursor: wait;
      }
      
      #lawmate-sync-button.disabled {
        opacity: 0.6;
        cursor: not-allowed;
        pointer-events: none;
      }
      
      #lawmate-sync-button img {
        width: 24px;
        height: 24px;
      }
      
      /* Notification Container */
      .lawmate-notification-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-width: 400px;
      }
      
      .lawmate-notification {
        background: white;
        padding: 16px 20px;
        border-radius: 10px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        display: flex;
        align-items: flex-start;
        gap: 12px;
        animation: slideInRight 0.3s ease-out;
        border-left: 4px solid #667eea;
      }
      
      .lawmate-notification.notification-success {
        border-left-color: #28a745;
      }
      
      .lawmate-notification.notification-error {
        border-left-color: #dc3545;
      }
      
      .lawmate-notification.notification-warning {
        border-left-color: #ffc107;
      }
      
      .notification-icon {
        font-size: 24px;
        flex-shrink: 0;
      }
      
      .notification-content {
        flex: 1;
      }
      
      .notification-title {
        font-weight: 600;
        font-size: 14px;
        margin-bottom: 4px;
        color: #212529;
      }
      
      .notification-message {
        font-size: 13px;
        color: #6c757d;
        line-height: 1.4;
      }
      
      .notification-close {
        background: none;
        border: none;
        font-size: 20px;
        color: #6c757d;
        cursor: pointer;
        padding: 0;
        line-height: 1;
        opacity: 0.6;
        transition: opacity 0.2s;
      }
      
      .notification-close:hover {
        opacity: 1;
      }
      
      @keyframes slideInRight {
        from {
          transform: translateX(400px);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
      
      @keyframes slideOutRight {
        from {
          transform: translateX(0);
          opacity: 1;
        }
        to {
          transform: translateX(400px);
          opacity: 0;
        }
      }
      
      /* Loading overlay */
      .lawmate-loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 9998;
        display: flex;
        align-items: center;
        justify-content: center;
        backdrop-filter: blur(4px);
      }
      
      .lawmate-loading-content {
        background: white;
        padding: 32px 48px;
        border-radius: 16px;
        text-align: center;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
      }
      
      .lawmate-spinner {
        width: 48px;
        height: 48px;
        border: 4px solid #f3f3f3;
        border-top: 4px solid #667eea;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 16px;
      }
      
      .lawmate-loading-text {
        font-size: 16px;
        font-weight: 600;
        color: #333;
        margin-bottom: 8px;
      }
      
      .lawmate-loading-subtext {
        font-size: 13px;
        color: #6c757d;
      }
      
      /* Tooltip */
      .lawmate-tooltip {
        position: absolute;
        background: #333;
        color: white;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 12px;
        white-space: nowrap;
        z-index: 10001;
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.2s;
      }
      
      .lawmate-tooltip.visible {
        opacity: 1;
      }
    `;
    
    document.head.appendChild(style);
  }
  
  /**
   * Inject sync status column to case table
   */
  injectSyncColumn() {
    const table = document.querySelector('#myCasesTable, table.cases-table, .case-list-table');
    if (!table) {
      Logger.warn('Case table not found, cannot inject sync column');
      return;
    }
    
    // Add header
    const headerRow = table.querySelector('thead tr');
    if (headerRow) {
      const th = document.createElement('th');
      th.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <img src="${chrome.runtime.getURL('assets/icon16.png')}" width="16" height="16" />
          <span>Lawmate Sync</span>
        </div>
      `;
      th.style.minWidth = '140px';
      headerRow.appendChild(th);
    }
    
    // Add status cells to each row
    const bodyRows = table.querySelectorAll('tbody tr');
    bodyRows.forEach((row, index) => {
      const td = document.createElement('td');
      td.classList.add('lawmate-status-cell');
      td.setAttribute('data-row-index', index);
      td.innerHTML = this.getStatusHTML('pending');
      row.appendChild(td);
    });
    
    Logger.info(`Injected sync column to ${bodyRows.length} rows`);
  }
  
  /**
   * Get HTML for status indicator
   */
  getStatusHTML(status, progress = 0, message = '') {
    const configs = {
      pending: {
        icon: '⏳',
        label: 'Pending Sync',
        cssClass: 'status-pending'
      },
      syncing: {
        icon: '🔄',
        label: 'Syncing...',
        cssClass: 'status-syncing'
      },
      uploading: {
        icon: '⬆️',
        label: `Uploading ${progress}%`,
        cssClass: 'status-uploading'
      },
      success: {
        icon: '✅',
        label: 'Synced',
        cssClass: 'status-success'
      },
      completed: {
        icon: '✅',
        label: 'Synced',
        cssClass: 'status-success'
      },
      failed: {
        icon: '❌',
        label: 'Failed',
        cssClass: 'status-failed'
      }
    };
    
    const config = configs[status] || configs.pending;
    
    let html = `
      <div class="lawmate-sync-status ${config.cssClass}">
        <span class="status-icon ${status === 'syncing' || status === 'uploading' ? 'spinning' : ''}">${config.icon}</span>
        <span class="status-text">${config.label}</span>
      </div>
    `;
    
    if (status === 'uploading' && progress > 0) {
      html += `
        <div class="upload-progress">
          <div class="upload-progress-bar" style="width: ${progress}%"></div>
        </div>
      `;
    }
    
    if (message) {
      html += `<div class="status-message" style="font-size: 11px; color: #6c757d; margin-top: 4px;">${message}</div>`;
    }
    
    return html;
  }
  
  /**
   * Update status for a specific case
   */
  updateStatus(caseNumber, documentId, status, progress = 0, message = '') {
    this.statusMap.set(caseNumber, { status, progress, message });
    
    // Find the row with this case number
    const rows = document.querySelectorAll('tbody tr');
    rows.forEach(row => {
      const caseCell = row.querySelector('td:first-child');
      if (caseCell && caseCell.textContent.includes(caseNumber)) {
        const statusCell = row.querySelector('.lawmate-status-cell');
        if (statusCell) {
          statusCell.innerHTML = this.getStatusHTML(status, progress, message);
        }
      }
    });
  }
  
  /**
   * Inject floating sync button
   */
  injectSyncButton() {
    if (document.getElementById('lawmate-sync-button')) return;
    
    const button = document.createElement('button');
    button.id = 'lawmate-sync-button';
    button.innerHTML = `
      <img src="${chrome.runtime.getURL('assets/icon16.png')}" />
      <span id="sync-button-text">Sync to Lawmate</span>
    `;
    
    button.addEventListener('click', () => {
      this.triggerSync();
    });
    
    document.body.appendChild(button);
    this.syncButton = button;
  }
  
  /**
   * Update sync button state
   */
  updateSyncButton(state) {
    if (!this.syncButton) return;
    
    const textElement = this.syncButton.querySelector('#sync-button-text');
    
    switch (state) {
      case 'syncing':
        this.syncButton.classList.add('syncing');
        this.syncButton.disabled = true;
        textElement.textContent = 'Syncing...';
        break;
      
      case 'success':
        this.syncButton.classList.remove('syncing');
        this.syncButton.disabled = false;
        textElement.textContent = 'Sync Complete ✓';
        setTimeout(() => {
          textElement.textContent = 'Sync to Lawmate';
        }, 3000);
        break;
      
      case 'error':
        this.syncButton.classList.remove('syncing');
        this.syncButton.disabled = false;
        textElement.textContent = 'Sync Failed - Retry';
        break;
      
      default:
        this.syncButton.classList.remove('syncing');
        this.syncButton.disabled = false;
        textElement.textContent = 'Sync to Lawmate';
    }
  }
  
  /**
   * Inject notification container
   */
  injectNotificationContainer() {
    if (document.querySelector('.lawmate-notification-container')) return;
    
    const container = document.createElement('div');
    container.className = 'lawmate-notification-container';
    document.body.appendChild(container);
  }
  
  /**
   * Show notification
   */
  showNotification(message, type = 'info', duration = 5000) {
    const container = document.querySelector('.lawmate-notification-container');
    if (!container) return;
    
    const icons = {
      success: '✅',
      error: '❌',
      warning: '⚠️',
      info: 'ℹ️'
    };
    
    const titles = {
      success: 'Success',
      error: 'Error',
      warning: 'Warning',
      info: 'Information'
    };
    
    const notification = document.createElement('div');
    notification.className = `lawmate-notification notification-${type}`;
    notification.innerHTML = `
      <span class="notification-icon">${icons[type]}</span>
      <div class="notification-content">
        <div class="notification-title">${titles[type]}</div>
        <div class="notification-message">${message}</div>
      </div>
      <button class="notification-close">×</button>
    `;
    
    const closeButton = notification.querySelector('.notification-close');
    closeButton.addEventListener('click', () => {
      this.dismissNotification(notification);
    });
    
    container.appendChild(notification);
    
    if (duration > 0) {
      setTimeout(() => {
        this.dismissNotification(notification);
      }, duration);
    }
  }
  
  /**
   * Dismiss notification
   */
  dismissNotification(notification) {
    notification.style.animation = 'slideOutRight 0.3s ease-out';
    setTimeout(() => {
      notification.remove();
    }, 300);
  }
  
  /**
   * Show loading overlay
   */
  showLoadingOverlay(message = 'Processing...', subtext = '') {
    const existing = document.querySelector('.lawmate-loading-overlay');
    if (existing) return;
    
    const overlay = document.createElement('div');
    overlay.className = 'lawmate-loading-overlay';
    overlay.innerHTML = `
      <div class="lawmate-loading-content">
        <div class="lawmate-spinner"></div>
        <div class="lawmate-loading-text">${message}</div>
        ${subtext ? `<div class="lawmate-loading-subtext">${subtext}</div>` : ''}
      </div>
    `;
    
    document.body.appendChild(overlay);
  }

  /**
   * Update loading overlay text while sync is in progress.
   */
  updateLoadingOverlay(message = '', subtext = '') {
    const overlay = document.querySelector('.lawmate-loading-overlay');
    if (!overlay) return;

    const textEl = overlay.querySelector('.lawmate-loading-text');
    const subtextEl = overlay.querySelector('.lawmate-loading-subtext');

    if (message && textEl) {
      textEl.textContent = message;
    }

    if (subtextEl) {
      subtextEl.textContent = subtext;
    } else if (subtext) {
      const content = overlay.querySelector('.lawmate-loading-content');
      if (content) {
        const div = document.createElement('div');
        div.className = 'lawmate-loading-subtext';
        div.textContent = subtext;
        content.appendChild(div);
      }
    }
  }
  
  /**
   * Hide loading overlay
   */
  hideLoadingOverlay() {
    const overlay = document.querySelector('.lawmate-loading-overlay');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.remove(), 300);
    }
  }
  
  /**
   * Trigger sync process
   */
  triggerSync() {
    const event = new CustomEvent('lawmate:trigger-sync');
    document.dispatchEvent(event);
  }
  
  /**
   * Attach event listeners
   */
  attachEventListeners() {
    // Listen for window visibility changes
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        Logger.debug('Page became visible, checking sync status');
      }
    });
  }
}

// ============================================================================
// Main Content Script Logic
// ============================================================================

class LawmateContentScript {
  constructor() {
    this.parser = new KHCDOMParser();
    this.ui = new LawmateUI();
    this.identity = null;
    this.cases = [];
    this.isInitialized = false;
    this.syncInProgress = false;
    this.listenersAttached = false;
  }
  
  /**
   * Initialize content script
   */
  async initialize() {
    Logger.info('Lawmate Content Script Initializing...', { 
      url: window.location.href,
      timestamp: new Date().toISOString()
    });
    
    try {
      // Wait for page to fully load
      if (document.readyState !== 'complete') {
        await new Promise(resolve => {
          window.addEventListener('load', resolve);
        });
      }
      
      // Additional wait for dynamic content (KHC portal may load data via AJAX)
      await this.waitForContent();
      
      // Initialize UI
      this.ui.initialize();

      // Always attach listeners early so popup/background messages can reach us
      // even if case rows are still loading.
      this.setupEventListeners();
      
      // Step 1: Extract advocate identity
      Logger.info('Step 1: Extracting advocate identity...');
      this.identity = this.parser.extractAdvocateIdentity();
      
      if (!this.identity) {
        this.ui.showNotification(
          'Cannot identify logged-in advocate. Please refresh the page.',
          'error',
          0
        );
        return;
      }
      
      Logger.info('Advocate identity extracted', { name: this.identity.name });
      
      // Step 2: Verify identity with backend
      Logger.info('Step 2: Verifying identity with Lawmate backend...');
      const verificationResult = await this.verifyIdentity();
      
      if (!verificationResult.verified) {
        this.ui.showNotification(
          verificationResult.message || 'Identity verification failed',
          'error',
          0
        );
        Logger.error('Identity verification failed', verificationResult);
        return;
      }
      
      Logger.info('Identity verified successfully');
      this.ui.showNotification(
        `Connected as ${this.identity.name}`,
        'success',
        3000
      );
      
      // Step 3: Parse cases from table
      Logger.info('Step 3: Parsing cases from table...');
      this.cases = this.parser.parseCaseTable();
      
      if (this.cases.length === 0) {
        Logger.warn('No cases found on page');
        this.ui.showNotification(
          'No cases found yet. Page may still be loading; you can retry sync shortly.',
          'warning',
          5000
        );
      } else {
        Logger.info(`Found ${this.cases.length} cases on page`);
      }
      
      // Step 5: Check for auto-sync
      await this.checkAutoSync();
      
      this.isInitialized = true;
      Logger.info(`Lawmate initialized successfully. Ready to sync ${this.cases.length} cases.`);
      
    } catch (error) {
      Logger.error('Initialization failed', { 
        error: error.message, 
        stack: error.stack 
      });
      this.ui.showNotification(
        'Failed to initialize Lawmate. Please refresh the page.',
        'error',
        0
      );
    }
  }
  
  /**
   * Wait for case table to load (handles AJAX-loaded content)
   */
  async waitForContent(maxWait = 25000) {
    const startTime = Date.now();
    
    while (Date.now() - startTime < maxWait) {
      const table = document.querySelector('#mycase-pet-table, #mycase-res-table, #mycase-amicus-table, #myCasesTable, table.cases-table, .case-list-table');
      if (table && table.querySelectorAll('tbody tr').length > 0) {
        Logger.debug('Case table found and populated');
        return true;
      }
      
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    Logger.warn('Timed out waiting for case table to load');
    return false;
  }
  
  /**
   * Verify identity with backend
   */
  async verifyIdentity() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: MESSAGE_TYPES.VERIFY_IDENTITY,
        data: this.identity
      }, (response) => {
        if (chrome.runtime.lastError) {
          Logger.error('Identity verification message failed', { 
            error: chrome.runtime.lastError.message 
          });
          resolve({ 
            verified: false, 
            error: 'Communication error with extension background script' 
          });
        } else {
          resolve(response);
        }
      });
    });
  }
  
  /**
   * Trigger case sync
   */
  async triggerSync(casesToSync = this.cases) {
    if (this.syncInProgress) {
      Logger.warn('Sync already in progress');
      return;
    }

    let targetCases = casesToSync;
    if (!targetCases || targetCases.length === 0) {
      Logger.info('No cached cases at sync start; reparsing table...');
      targetCases = await this.refreshCasesFromDOM();
    }

    if (!targetCases || targetCases.length === 0) {
      this.ui.showNotification('No cases to sync', 'warning');
      return;
    }
    
    this.syncInProgress = true;
    
    Logger.info(`Initiating sync for ${targetCases.length} cases`);
    
    // Update UI
    this.ui.updateSyncButton('syncing');
    this.ui.showLoadingOverlay(
      `Syncing ${targetCases.length} cases...`,
      `This may take a few minutes... (0/${targetCases.length})`
    );
    
    // Enrich with case-bundle links from caseDetails API (no manual "Details" click needed)
    const enrichment = await this.enrichCasesWithCaseBundleLinks(targetCases);
    const enrichedCases = enrichment.cases;

    this.ui.showNotification(
      `Case bundle fetched for ${enrichment.bundleCaseCount}/${enrichment.totalCases} case(s).`,
      enrichment.bundleCaseCount > 0 ? 'info' : 'warning',
      5000
    );

    // Update all case statuses to syncing
    enrichedCases.forEach(caseData => {
      this.ui.updateStatus(caseData.case_number || caseData.efiling_number, null, 'syncing');
    });
    
    try {
      // Send to background script
      const response = await new Promise((resolve) => {
        chrome.runtime.sendMessage({
          action: MESSAGE_TYPES.SYNC_CASES,
          data: {
            identity: this.identity,
            cases: enrichedCases
          }
        }, resolve);
      });
      
      if (chrome.runtime.lastError) {
        throw new Error(chrome.runtime.lastError.message);
      }
      
      if (response.status === 'success' || response.status === 'sync_started') {
        Logger.info('Sync initiated successfully');
        this.ui.updateSyncButton('success');
        this.ui.showNotification(
          `Syncing ${targetCases.length} cases to Lawmate. Check your dashboard for updates.`,
          'success',
          5000
        );
      } else {
        throw new Error(response.error || 'Sync failed');
      }
      
    } catch (error) {
      Logger.error('Sync failed', { error: error.message });
      this.ui.updateSyncButton('error');
      this.ui.showNotification(
        `Sync failed: ${error.message}`,
        'error',
        10000
      );
      
      // Reset case statuses to pending
      enrichedCases.forEach(caseData => {
        this.ui.updateStatus(caseData.case_number || caseData.efiling_number, null, 'pending');
      });
      
    } finally {
      this.syncInProgress = false;
      this.ui.hideLoadingOverlay();
    }
  }
  
  /**
   * Check if auto-sync should be triggered
   */
  async checkAutoSync() {
    // Get user preferences from storage (supports both legacy and current keys)
    const stored = await chrome.storage.local.get(['auto_sync', CONFIG.STORAGE_KEYS.USER_PROFILE]);
    const profileAutoSync = stored?.[CONFIG.STORAGE_KEYS.USER_PROFILE]?.preferences?.auto_sync;
    const autoSyncEnabled = typeof stored.auto_sync === 'boolean'
      ? stored.auto_sync
      : profileAutoSync === true;
    
    if (autoSyncEnabled) {
      Logger.info('Auto-sync is enabled, scheduling sync with retries...');
      this.startAutoSyncWithRetries();
    }
  }

  /**
   * Start auto-sync with retries to handle delayed page/data loads.
   */
  startAutoSyncWithRetries(maxAttempts = 6, delayMs = 5000) {
    let attempt = 0;
    const run = async () => {
      if (this.syncInProgress) return;
      attempt += 1;
      Logger.info('Auto-sync attempt', { attempt, maxAttempts });

      const cases = await this.refreshCasesFromDOM();
      if (cases && cases.length > 0) {
        this.triggerSync(cases);
        return;
      }

      if (attempt < maxAttempts) {
        setTimeout(run, delayMs);
      } else {
        Logger.warn('Auto-sync retries exhausted: no cases found');
      }
    };

    // Give initial render a short head-start.
    setTimeout(run, 2000);
  }

  /**
   * Re-read case rows from DOM after waiting for dynamic DataTable load.
   */
  async refreshCasesFromDOM() {
    await this.waitForContent(30000);
    this.cases = this.parser.parseCaseTable();
    if (this.cases.length > 0) {
      Logger.info(`Cases refreshed from DOM: ${this.cases.length}`);
    } else {
      Logger.warn('Cases still unavailable after refresh attempt');
    }
    return this.cases;
  }
  
  /**
   * Setup event listeners
   */
  setupEventListeners() {
    if (this.listenersAttached) return;
    this.listenersAttached = true;

    // Listen for sync trigger from button
    document.addEventListener('lawmate:trigger-sync', () => {
      this.triggerSync();
    });
    
    // Listen for updates from background script
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      try {
        if (request.action === MESSAGE_TYPES.UPDATE_STATUS) {
          this.handleStatusUpdate(request);
        }
        
        if (request.action === MESSAGE_TYPES.UPDATE_PROGRESS) {
          this.handleProgressUpdate(request);
        }

        if (request.action === MESSAGE_TYPES.UPDATE_SYNC_PROGRESS) {
          this.handleSyncProgressUpdate(request);
        }
        
        if (request.action === MESSAGE_TYPES.TRIGGER_AUTO_SYNC) {
          Logger.info('Auto-sync triggered by background script');
          this.startAutoSyncWithRetries();
        }

        if (request.action === MESSAGE_TYPES.SYNC_SELECTED_CASE) {
          this.syncSelectedCase(request.selectedText);
        }
        
        if (request.action === MESSAGE_TYPES.SHOW_ERROR) {
          this.ui.showNotification(request.message, 'error', 10000);
        }
        
        sendResponse({ received: true });
      } catch (error) {
        Logger.error('Message handler error', { error: error.message });
        sendResponse({ error: error.message });
      }
      
      return true; // Keep channel open for async response
    });
    
    // Listen for page unload
    window.addEventListener('beforeunload', () => {
      if (this.syncInProgress) {
        Logger.warn('Page unloading during sync');
      }
    });
  }
  
  /**
   * Handle status update from background script
   */
  handleStatusUpdate(request) {
    const { case_number, document_id, status, s3_key, error } = request;
    
    let message = '';
    if (error) {
      message = `Error: ${error}`;
    } else if (s3_key) {
      message = 'Uploaded successfully';
    }
    
    this.ui.updateStatus(case_number, document_id, status, 0, message);
    
    // Show notification for failures
    if (status === 'failed') {
      this.ui.showNotification(
        `Failed to sync case ${case_number}: ${error}`,
        'error',
        8000
      );
    }
  }
  
  /**
   * Handle progress update from background script
   */
  handleProgressUpdate(request) {
    const { case_number, document_id, progress } = request;
    this.ui.updateStatus(case_number, document_id, 'uploading', progress);
  }

  /**
   * Handle overall sync progress updates.
   */
  handleSyncProgressUpdate(request) {
    const processed = Number(request.processed_cases || 0);
    const total = Number(request.total_cases || 0);
    if (!total) return;

    this.ui.updateLoadingOverlay(
      `Syncing ${total} cases...`,
      `This may take a few minutes... (${processed}/${total})`
    );
  }

  /**
   * Sync only selected case(s) from context-menu text.
   */
  syncSelectedCase(selectedText) {
    const normalizedText = (selectedText || '').trim().toLowerCase().replace(/\s+/g, '');
    if (!normalizedText) {
      this.ui.showNotification('Select a case number first and retry.', 'warning', 5000);
      return;
    }

    const selectedCases = this.cases.filter((caseData) => {
      const caseNumber = (caseData.case_number || '').toLowerCase().replace(/\s+/g, '');
      const efilingNumber = (caseData.efiling_number || '').toLowerCase().replace(/\s+/g, '');
      return caseNumber.includes(normalizedText) || efilingNumber.includes(normalizedText);
    });

    if (selectedCases.length === 0) {
      this.ui.showNotification('No matching case found for the selected text.', 'warning', 5000);
      return;
    }

    this.ui.showNotification(
      `Syncing ${selectedCases.length} selected case${selectedCases.length > 1 ? 's' : ''}...`,
      'info',
      3000
    );
    this.triggerSync(selectedCases);
  }

  /**
   * Build portal base path (e.g. https://host/digicourt/).
   */
  getPortalBasePath() {
    const marker = '/digicourt/';
    const index = window.location.pathname.toLowerCase().indexOf(marker);
    if (index >= 0) {
      return `${window.location.origin}${window.location.pathname.substring(0, index + marker.length)}`;
    }
    return `${window.location.origin}/digicourt/`;
  }

  /**
   * Resolve current page's DataTable AJAX endpoint.
   */
  resolveCaseListAjaxEndpoint() {
    const scriptsText = Array.from(document.scripts)
      .map((script) => script.textContent || '')
      .join('\n');

    const inlineMatch = scriptsText.match(/url:\s*path\s*\+\s*['"]([^'"]*mycase[^'"]*_ajax)['"]/i);
    if (inlineMatch?.[1]) {
      return `${this.getPortalBasePath()}${inlineMatch[1].replace(/^\/+/, '')}`;
    }

    const path = window.location.pathname.toLowerCase();
    if (path.includes('/mycasepet')) {
      return `${this.getPortalBasePath()}Mycasesnew/mycasePet_ajax`;
    }
    if (path.includes('/mycaseres')) {
      return `${this.getPortalBasePath()}Mycasesnew/mycaseRes_ajax`;
    }
    if (path.includes('/mycasesamicus')) {
      return `${this.getPortalBasePath()}Mycasesnew/mycaseAmicus_ajax`;
    }

    return null;
  }

  /**
   * Read current UI filter values from DigiCourt search controls.
   */
  getCurrentCaseFilters() {
    return {
      cstat: document.querySelector('input[name="case_status"]:checked')?.value || '1',
      kw_efileno: document.getElementById('efileno')?.value || '',
      cfrno: document.getElementById('cfrno')?.value || '',
      partyname: document.getElementById('partyname')?.value || '',
      pip: Boolean(document.querySelector('input[name="pip"]')?.checked),
      cia: Boolean(document.querySelector('input[name="cia"]')?.checked),
      cvt: Boolean(document.querySelector('input[name="cvt"]')?.checked)
    };
  }

  /**
   * CSRF token helper from cookie.
   */
  getCSRFTokenFromCookie() {
    const match = document.cookie.match(/(?:^|;\s*)CSRFToken=([^;]+)/);
    return match?.[1] || '';
  }

  /**
   * Fetch DataTable rows for current My Cases page.
   */
  async fetchCaseRowsForCurrentView() {
    const endpoint = this.resolveCaseListAjaxEndpoint();
    if (!endpoint) {
      Logger.warn('Could not resolve case list AJAX endpoint');
      return [];
    }

    const filters = this.getCurrentCaseFilters();
    const rows = [];
    const pageSize = 100;
    let start = 0;
    let draw = 1;
    let total = pageSize;
    let safety = 0;

    while (start < total && safety < 30) {
      const body = new URLSearchParams({
        draw: String(draw),
        start: String(start),
        length: String(pageSize),
        cstat: String(filters.cstat),
        kw_efileno: String(filters.kw_efileno),
        cfrno: String(filters.cfrno),
        partyname: String(filters.partyname),
        pip: String(filters.pip),
        cia: String(filters.cia),
        cvt: String(filters.cvt)
      });

      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRF-Token': this.getCSRFTokenFromCookie()
        },
        body: body.toString()
      });

      if (!response.ok) {
        throw new Error(`CASE_LIST_FETCH_FAILED: ${response.status} ${response.statusText}`);
      }

      const json = await response.json();
      const dataRows = Array.isArray(json.data) ? json.data : [];
      rows.push(...dataRows);

      total = Number(json.recordsFiltered ?? json.recordsTotal ?? dataRows.length);
      if (dataRows.length === 0) {
        break;
      }

      start += dataRows.length;
      draw += 1;
      safety += 1;
    }

    return rows;
  }

  /**
   * Parse case bundle links from caseDetails HTML response.
   */
  extractBundleLinksFromCaseDetailsHTML(caseDetailsHTML) {
    const temp = document.createElement('div');
    temp.innerHTML = caseDetailsHTML;

    const buttons = temp.querySelectorAll('button[onclick*="PrintCaseBundle"]');
    const links = [];
    const basePath = this.getPortalBasePath();

    buttons.forEach((button, index) => {
      const onclick = button.getAttribute('onclick') || '';
      const parsed = this.parser.parsePrintCaseBundleOnclick(onclick);
      if (!parsed) return;

      const bundleUrl = `${basePath}Casebundle/loadBundle?token=${encodeURIComponent(parsed.etype)}&salt=${encodeURIComponent(parsed.efile_id)}&pds=${encodeURIComponent(parsed.pd)}&cnr=${encodeURIComponent(parsed.cino)}&cny=${encodeURIComponent(parsed.ctitle)}`;

      links.push({
        url: bundleUrl,
        document_id: `bundle-${this.parser.hashCode(bundleUrl)}`,
        label: button.textContent.trim() || `Case Bundle ${index + 1}`,
        category: 'case_bundle'
      });
    });

    return links;
  }

  /**
   * Fetch case bundle links via Mycasesnew/caseDetails for one row.
   */
  async fetchBundleLinksForCaseRow(rowData) {
    const eidEnc = rowData?.eid_enc || rowData?.efile_id_enc;
    const hasAll = Boolean(
      rowData?.cino &&
      rowData?.efile_no &&
      eidEnc &&
      rowData?.ctype_enc &&
      rowData?.sub_enc &&
      rowData?.case_pd &&
      rowData?.ctitle
    );
    if (!hasAll) {
      return [];
    }

    const params = new URLSearchParams({
      cino: rowData.cino,
      efile_no: rowData.efile_no,
      dgtzn_no: rowData.dgtzn_no || '',
      eid_enc: eidEnc,
      ctype_enc: rowData.ctype_enc,
      sub_enc: rowData.sub_enc,
      case_pd: rowData.case_pd,
      ctitle: rowData.ctitle
    });

    const url = `${this.getPortalBasePath()}Mycasesnew/caseDetails?${params.toString()}`;
    const response = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-Token': this.getCSRFTokenFromCookie()
      }
    });

    if (!response.ok) {
      throw new Error(`CASE_DETAILS_FETCH_FAILED: ${response.status}`);
    }

    const json = await response.json();
    const html = typeof json?.html === 'string' ? json.html : '';
    if (!html) return [];

    return this.extractBundleLinksFromCaseDetailsHTML(html);
  }

  /**
   * Enrich cases with bundle links from server-side case details API.
   */
  async enrichCasesWithCaseBundleLinks(casesToSync) {
    try {
      Logger.info('Fetching case bundle links from caseDetails API');
      const rows = await this.fetchCaseRowsForCurrentView();

      const wantedKeys = new Set(
        casesToSync.flatMap((c) => ([
          (c.efiling_number || '').toLowerCase().replace(/\s+/g, ''),
          (c.case_number || '').toLowerCase().replace(/\s+/g, ''),
          (c.case_number || '').toLowerCase().replace(/[^a-z0-9]/g, '')
        ])).filter(Boolean)
      );

      const bundleMap = new Map();

      for (const rowData of rows) {
        if (!rowData || typeof rowData !== 'object') continue;

        const rowEfile = String(rowData.efile_no || '').toLowerCase().replace(/\s+/g, '');
        const decodedTitle = this.decodeBase64Safe(rowData.ctitle || '');
        const rowCase = String(decodedTitle || '').toLowerCase().replace(/\s+/g, '');
        const rowCaseCompact = rowCase.replace(/[^a-z0-9]/g, '');

        if (
          wantedKeys.size > 0 &&
          !wantedKeys.has(rowEfile) &&
          !wantedKeys.has(rowCase) &&
          !wantedKeys.has(rowCaseCompact)
        ) {
          continue;
        }

        try {
          const links = await this.fetchBundleLinksForCaseRow(rowData);
          if (links.length > 0) {
            bundleMap.set(rowEfile, links);
            if (rowCase) bundleMap.set(rowCase, links);
            if (rowCaseCompact) bundleMap.set(rowCaseCompact, links);
          }
        } catch (error) {
          Logger.warn('Failed to fetch case details for row', {
            efile_no: rowData.efile_no,
            error: error.message
          });
        }
      }

      const cases = casesToSync.map((caseData) => {
        const efileKey = String(caseData.efiling_number || '').toLowerCase().replace(/\s+/g, '');
        const caseKey = String(caseData.case_number || '').toLowerCase().replace(/\s+/g, '');
        const caseCompact = caseKey.replace(/[^a-z0-9]/g, '');
        const bundleLinks = bundleMap.get(efileKey) || bundleMap.get(caseKey) || bundleMap.get(caseCompact) || [];

        return {
          ...caseData,
          pdf_links: bundleLinks
        };
      });

      const bundleCaseCount = cases.filter((c) => Array.isArray(c.pdf_links) && c.pdf_links.length > 0).length;
      const totalBundleLinks = cases.reduce((sum, c) => sum + (Array.isArray(c.pdf_links) ? c.pdf_links.length : 0), 0);

      Logger.info('Bundle link enrichment completed', {
        total_cases: cases.length,
        cases_with_bundle_links: bundleCaseCount,
        total_bundle_links: totalBundleLinks
      });

      return {
        cases,
        totalCases: cases.length,
        bundleCaseCount,
        totalBundleLinks
      };
    } catch (error) {
      Logger.error('Bundle enrichment failed, continuing with existing parsed links', {
        error: error.message
      });
      return {
        cases: casesToSync,
        totalCases: casesToSync.length,
        bundleCaseCount: 0,
        totalBundleLinks: 0
      };
    }
  }

  decodeBase64Safe(value) {
    if (!value || typeof value !== 'string') return '';
    try {
      return decodeURIComponent(escape(atob(value)));
    } catch (_) {
      try {
        return atob(value);
      } catch (__){
        return '';
      }
    }
  }
}

// ============================================================================
// Initialize Content Script
// ============================================================================

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeLawmate);
} else {
  initializeLawmate();
}

function initializeLawmate() {
  Logger.info('DOM ready, initializing Lawmate...');
  
  const lawmate = new LawmateContentScript();
  lawmate.initialize();
  
  // Make it globally accessible for debugging
  window.lawmate = lawmate;
}

// Handle SPA navigation (if KHC portal uses client-side routing)
let lastUrl = location.href;
new MutationObserver(() => {
  const url = location.href;
  if (url !== lastUrl) {
    lastUrl = url;
    Logger.info('URL changed, reinitializing...', { url });
    initializeLawmate();
  }
}).observe(document, { subtree: true, childList: true });

Logger.info('Lawmate content script loaded');


/* 
Configuration: You can customize behavior by modifying constants:
// Auto-sync delay
const AUTO_SYNC_DELAY = 2000; // 2 seconds

// Content wait timeout
const CONTENT_WAIT_TIMEOUT = 10000; // 10 seconds

// Notification durations
const NOTIFICATION_DURATION = {
  success: 5000,
  error: 10000,
  warning: 5000,
  info: 3000
}; */

/* 
Debugging
Access the content script instance in the browser console:
// Check if initialized
window.lawmate.isInitialized

// View extracted identity
window.lawmate.identity

// View parsed cases
window.lawmate.cases

// Manual sync trigger
window.lawmate.triggerSync()

// Check UI state
window.lawmate.ui.statusMap */

/* Key Features Implemented
1. Identity Extraction & Verification

Extracts KHC Advocate ID from multiple possible locations
Verifies with backend before allowing sync
Handles identity mismatch gracefully

2. Case Table Parsing

Uses the KHCDOMParser module
Handles dynamic content loading
Validates extracted data

3. UI Components

✅ Status column in case table
✅ Floating sync button
✅ Notification system
✅ Loading overlay
✅ Progress indicators

4. Sync Orchestration

Communicates with background script
Handles auto-sync preferences
Updates UI in real-time
Error handling and retry logic

5. Event Handling

Listens for messages from background script
Handles page visibility changes
Detects SPA navigation 
 Notes

Import statements require Webpack to bundle properly
Chrome extension URLs use chrome.runtime.getURL()
Message passing is async with callbacks
MutationObserver handles SPA navigation
*/
