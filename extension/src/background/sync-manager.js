// src/background/sync-manager.js

import { CONFIG, MESSAGE_TYPES, SYNC_STATUS, UPLOAD_STATUS } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { Storage } from '../utils/storage.js';
import { APIClient } from './api-client.js';
import { AuthManager } from './auth-manager.js';
import { UploadManager } from './upload-manager.js';

export class SyncManager {
  constructor() {
    this.apiClient = new APIClient();
    this.authManager = new AuthManager();
    this.uploadManager = new UploadManager();
    this.isSyncing = false;
  }
  
  /**
   * Verify identity handshake
   */
  async verifyIdentity(scrapedIdentity) {
    try {
      Logger.info('Verifying identity', { name: scrapedIdentity.name });
      
      await this.authManager.ensureAuthenticated();
      
      const verifyEndpoint =
        `${CONFIG.ENDPOINTS.VERIFY_IDENTITY}?scraped_name=${encodeURIComponent(scrapedIdentity.name)}`;

      const response = await this.apiClient.post(verifyEndpoint, {});
      
      if (!response.verified) {
        Logger.error('Identity mismatch detected', {
          scraped: scrapedIdentity.name,
          expected: response.advocate_name
        });
        
        // Security breach: Clear all data
        await this.authManager.clearSession();
        
        // Show critical notification
        await chrome.notifications.create({
          type: 'basic',
          iconUrl: chrome.runtime.getURL('assets/icon48.png'),
          title: 'Lawmate Security Alert',
          message: response.message || CONFIG.ERRORS.IDENTITY_MISMATCH,
          priority: 2
        });
      }
      
      return response;
      
    } catch (error) {
      Logger.error('Identity verification failed', { error: error.message });
      return {
        verified: false,
        message: error.message,
        error: error.message
      };
    }
  }
  
  /**
   * Sync cases and documents
   */
  async syncCases(payload) {
    if (this.isSyncing) {
      Logger.warn('Sync already in progress, skipping...');
      return { status: 'already_syncing' };
    }
    
    this.isSyncing = true;
    
    try {
      const { identity, cases, sync_token } = payload;
      
      Logger.info(`Starting sync for ${cases.length} cases`);
      
      // Update sync status
      await Storage.set(CONFIG.STORAGE_KEYS.SYNC_STATUS, SYNC_STATUS.SYNCING);
      
      let processedCases = 0;
      const totalCases = cases.length;
      for (const caseData of cases) {
        try {
          // Step 1: Sync case metadata
          await this.syncCaseMetadata(caseData, identity);
          
          // Step 2: Sync documents
          await this.syncCaseDocuments(caseData, identity);
          
        } catch (error) {
          Logger.error(`Failed to sync case ${caseData.case_number}`, { 
            error: error.message 
          });
          // Continue with next case
        } finally {
          processedCases += 1;
          this.updateSyncProgress(processedCases, totalCases, caseData.case_number);
        }
      }
      
      // Update last sync timestamp
      await Storage.set(CONFIG.STORAGE_KEYS.LAST_SYNC, Date.now());
      await Storage.set(CONFIG.STORAGE_KEYS.SYNC_STATUS, SYNC_STATUS.SUCCESS);
      
      Logger.info('Sync completed successfully');
      
      return { status: 'success' };
      
    } catch (error) {
      Logger.error('Sync failed', { error: error.message });
      await Storage.set(CONFIG.STORAGE_KEYS.SYNC_STATUS, SYNC_STATUS.FAILED);
      
      return { 
        status: 'error', 
        error: error.message 
      };
      
    } finally {
      this.isSyncing = false;
    }
  }
  
  /**
   * Sync case metadata to backend
   */
  async syncCaseMetadata(caseData, identity) {
    Logger.debug('Syncing case metadata', { 
      case_number: caseData.case_number 
    });
    
    await this.authManager.ensureAuthenticated();
    
    const payload = {
      efiling_number: caseData.efiling_number,
      case_number: caseData.case_number,
      case_type: caseData.case_type,
      case_year: caseData.case_year,
      party_role: caseData.party_role,
      petitioner_name: caseData.petitioner_name,
      respondent_name: caseData.respondent_name,
      efiling_date: caseData.efiling_date,
      efiling_details: caseData.efiling_details,
      next_hearing_date: caseData.next_hearing_date,
      status: caseData.status,
      bench_type: caseData.bench_type,
      judge_name: caseData.judge_name,
      khc_source_url: caseData.khc_source_url,
      khc_id: identity.khc_id,
      khc_name: identity.name
    };
    
    const response = await this.apiClient.post(CONFIG.ENDPOINTS.SYNC_CASES, payload);
    
    Logger.debug('Case metadata synced', { 
      case_id: response.case_id 
    });
    
    return response;
  }
  
  /**
   * Sync case documents
   */
  async syncCaseDocuments(caseData, identity) {
    if (!caseData.pdf_links || caseData.pdf_links.length === 0) {
      Logger.debug('No documents to sync', { 
        case_number: caseData.case_number 
      });
      return;
    }
    
    Logger.info(`Syncing ${caseData.pdf_links.length} documents`, {
      case_number: caseData.case_number
    });
    
    for (const pdfLink of caseData.pdf_links) {
      try {
        await this.syncDocument(caseData, pdfLink);
      } catch (error) {
        Logger.error('Document sync failed', {
          case_number: caseData.case_number,
          document: pdfLink.label,
          error: error.message
        });
        
        // Update UI with error
        this.updateSyncStatus(
          caseData.case_number,
          pdfLink.document_id,
          UPLOAD_STATUS.FAILED,
          null,
          error.message
        );
      }
    }
  }
  
  /**
   * Sync single document
   */
  async syncDocument(caseData, pdfLink) {
    Logger.debug('Syncing document', {
      case_number: caseData.case_number,
      document: pdfLink.label
    });
    
    // Update UI: Starting upload
    this.updateSyncStatus(
      caseData.case_number,
      pdfLink.document_id,
      UPLOAD_STATUS.UPLOADING
    );
    
    // Phase A: Download PDF from KHC (with credentials)
    const pdfBlob = await this.fetchPDFFromKHC(pdfLink.url);
    
    // Phase B: Upload to S3
    const uploadResult = await this.uploadManager.upload(
      caseData.case_number,
      pdfLink.document_id,
      pdfBlob,
      {
        category: pdfLink.category,
        title: pdfLink.label,
        source_url: pdfLink.url
      }
    );
    
    // Phase C: Update backend with document metadata
    await this.authManager.ensureAuthenticated();
    
    await this.apiClient.post(CONFIG.ENDPOINTS.SYNC_DOCUMENTS, {
      case_number: caseData.case_number,
      khc_document_id: pdfLink.document_id,
      category: pdfLink.category,
      title: pdfLink.label,
      s3_key: uploadResult.s3_key,
      file_size: pdfBlob.size,
      source_url: pdfLink.url
    });
    
    // Update UI: Success
    this.updateSyncStatus(
      caseData.case_number,
      pdfLink.document_id,
      UPLOAD_STATUS.COMPLETED,
      uploadResult.s3_key
    );
    
    Logger.info('Document synced successfully', {
      case_number: caseData.case_number,
      s3_key: uploadResult.s3_key
    });
  }
  
  /**
   * Fetch PDF from KHC portal (Phase A)
   */
  async fetchPDFFromKHC(pdfUrl) {
    Logger.debug('Downloading PDF from KHC', { url: pdfUrl });
    
    try {
      // The magic: credentials: 'include' auto-attaches httpOnly cookies
      const response = await fetch(pdfUrl, {
        method: 'GET',
        credentials: 'include', // ← Auto cookie injection
        headers: {
          'Accept': 'application/pdf'
        }
      });
      
      if (!response.ok) {
        throw new Error(`KHC returned ${response.status}: ${response.statusText}`);
      }
      
      const blob = await response.blob();
      
      // Validate PDF
      if (!blob.type.includes('pdf') && !blob.type.includes('application/octet-stream')) {
        Logger.warn(`Unexpected content type: ${blob.type}`);
      }
      
      Logger.debug(`PDF downloaded: ${(blob.size / 1024 / 1024).toFixed(2)} MB`);
      
      return blob;
      
    } catch (error) {
      Logger.error('PDF download failed', { url: pdfUrl, error: error.message });
      throw new Error(`KHC_FETCH_FAILED: ${error.message}`);
    }
  }
  
  /**
   * Update sync status in content script UI
   */
  updateSyncStatus(caseNumber, documentId, status, s3Key = null, error = null) {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: MESSAGE_TYPES.UPDATE_STATUS,
          case_number: caseNumber,
          document_id: documentId,
          status,
          s3_key: s3Key,
          error
        }).catch(() => {
          // Tab might be closed, ignore
        });
      }
    });
  }

  /**
   * Update overall case-sync progress in content script UI.
   */
  updateSyncProgress(processedCases, totalCases, caseNumber = null) {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: MESSAGE_TYPES.UPDATE_SYNC_PROGRESS,
          processed_cases: processedCases,
          total_cases: totalCases,
          case_number: caseNumber
        }).catch(() => {
          // Tab might be closed, ignore
        });
      }
    });
  }
}
