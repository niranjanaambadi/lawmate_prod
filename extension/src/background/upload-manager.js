// src/background/upload-manager.js

import { CONFIG, MESSAGE_TYPES } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { APIClient } from './api-client.js';
import { AuthManager } from './auth-manager.js';

export class UploadManager {
  constructor() {
    this.apiClient = new APIClient();
    this.authManager = new AuthManager();
    this.activeUploads = new Map();
  }
  
  /**
   * Upload PDF to S3 (smart routing: standard vs multipart)
   */
  async upload(caseNumber, documentId, pdfBlob, metadata = {}) {
    const fileSize = pdfBlob.size;
    
    Logger.info('Starting upload', { 
      caseNumber, 
      documentId, 
      fileSize: `${(fileSize / 1024 / 1024).toFixed(2)} MB` 
    });
    
    try {
      if (fileSize > CONFIG.MULTIPART_THRESHOLD) {
        return await this.multipartUpload(caseNumber, documentId, pdfBlob, metadata);
      } else {
        return await this.standardUpload(caseNumber, documentId, pdfBlob, metadata);
      }
    } catch (error) {
      Logger.error('Upload failed', { caseNumber, documentId, error: error.message });
      throw error;
    }
  }
  
  /**
   * Standard upload (< 15MB)
   */
  async standardUpload(caseNumber, documentId, pdfBlob, metadata) {
    Logger.debug('Using standard upload', { caseNumber, documentId });
    
    // Get pre-signed URL
    await this.authManager.ensureAuthenticated();
    
    const urlResponse = await this.apiClient.post(CONFIG.ENDPOINTS.PRESIGNED_URL, {
      case_number: caseNumber,
      document_id: documentId,
      file_size: pdfBlob.size,
      ...metadata
    });
    
    const { upload_url, s3_key, headers: requiredHeaders = {} } = urlResponse;
    const uploadHeaders = {
      ...requiredHeaders
    };
    if (!uploadHeaders['Content-Type']) {
      uploadHeaders['Content-Type'] = 'application/pdf';
    }
    
    // Upload to S3
    const uploadResponse = await fetch(upload_url, {
      method: 'PUT',
      body: pdfBlob,
      headers: uploadHeaders
    });
    
    if (!uploadResponse.ok) {
      throw new Error(`S3 upload failed: ${uploadResponse.status} ${uploadResponse.statusText}`);
    }
    
    Logger.info('Standard upload completed', { s3_key });
    
    return { s3_key, upload_method: 'standard' };
  }
  
  /**
   * Multipart upload (>= 15MB)
   */
  async multipartUpload(caseNumber, documentId, pdfBlob, metadata) {
    Logger.info('Using multipart upload', { 
      caseNumber, 
      documentId,
      fileSize: `${(pdfBlob.size / 1024 / 1024).toFixed(2)} MB`
    });
    
    await this.authManager.ensureAuthenticated();
    
    // Step 1: Initiate multipart upload
    const initResponse = await this.apiClient.post(CONFIG.ENDPOINTS.MULTIPART_INIT, {
      case_number: caseNumber,
      document_id: documentId,
      file_size: pdfBlob.size,
      chunk_size: CONFIG.CHUNK_SIZE,
      ...metadata
    });
    
    const { upload_id, chunk_urls, s3_key, total_parts } = initResponse;
    
    Logger.debug('Multipart upload initiated', { upload_id, total_parts });
    
    try {
      // Step 2: Split blob and upload chunks
      const chunks = this.splitBlob(pdfBlob, CONFIG.CHUNK_SIZE);
      
      const uploadedParts = await this.uploadChunksWithRetry(
        chunks,
        chunk_urls,
        upload_id,
        caseNumber,
        documentId
      );
      
      // Step 3: Complete multipart upload
      await this.authManager.ensureAuthenticated();
      
      const completeResponse = await this.apiClient.post(CONFIG.ENDPOINTS.MULTIPART_COMPLETE, {
        upload_id,
        parts: uploadedParts,
        s3_key
      });
      
      Logger.info('Multipart upload completed', { s3_key });
      
      return { s3_key, upload_method: 'multipart', parts: total_parts };
      
    } catch (error) {
      // Abort multipart upload on failure
      Logger.error('Multipart upload failed, aborting...', { upload_id });
      
      try {
        await this.apiClient.delete(
          `${CONFIG.ENDPOINTS.MULTIPART_ABORT}/${upload_id}`,
          {
            body: { s3_key }
          }
        );
      } catch (abortError) {
        Logger.error('Failed to abort multipart upload', { abortError });
      }
      
      throw error;
    }
  }
  
  /**
   * Split blob into chunks
   */
  splitBlob(blob, chunkSize) {
    const chunks = [];
    let offset = 0;
    
    while (offset < blob.size) {
      const chunk = blob.slice(offset, offset + chunkSize);
      chunks.push(chunk);
      offset += chunkSize;
    }
    
    Logger.debug(`Split blob into ${chunks.length} chunks`);
    return chunks;
  }
  
  /**
   * Upload chunks with retry logic
   */
  async uploadChunksWithRetry(chunks, chunkUrls, uploadId, caseNumber, documentId) {
    const uploadedParts = [];
    const failedChunks = [];
    
    // Upload in batches
    for (let i = 0; i < chunks.length; i += CONFIG.CONCURRENT_UPLOADS) {
      const batch = chunks.slice(i, i + CONFIG.CONCURRENT_UPLOADS);
      const batchUrls = chunkUrls.slice(i, i + CONFIG.CONCURRENT_UPLOADS);
      
      const batchResults = await Promise.allSettled(
        batch.map((chunk, idx) => 
          this.uploadChunkWithRetry(
            chunk,
            batchUrls[idx],
            i + idx + 1 // Part number (1-based)
          )
        )
      );
      
      // Process results
      batchResults.forEach((result, idx) => {
        const partNumber = i + idx + 1;
        
        if (result.status === 'fulfilled') {
          uploadedParts.push({
            PartNumber: partNumber,
            ETag: result.value
          });
          
          // Update progress
          this.updateProgress(caseNumber, documentId, partNumber, chunks.length);
          
        } else {
          failedChunks.push({
            partNumber,
            chunk: batch[idx],
            url: batchUrls[idx],
            error: result.reason
          });
        }
      });
    }
    
    // Retry failed chunks
    if (failedChunks.length > 0) {
      Logger.warn(`Retrying ${failedChunks.length} failed chunks...`);
      
      for (const failed of failedChunks) {
        const etag = await this.uploadChunkWithRetry(
          failed.chunk,
          failed.url,
          failed.partNumber,
          CONFIG.MAX_RETRIES
        );
        
        uploadedParts.push({
          PartNumber: failed.partNumber,
          ETag: etag
        });
      }
    }
    
    // Sort by part number
    return uploadedParts.sort((a, b) => a.PartNumber - b.PartNumber);
  }
  
  /**
   * Upload single chunk with retry
   */
  async uploadChunkWithRetry(chunk, presignedUrl, partNumber, maxRetries = CONFIG.MAX_RETRIES) {
    let lastError;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await fetch(presignedUrl, {
          method: 'PUT',
          body: chunk
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        const etag = response.headers.get('ETag');
        if (!etag) {
          throw new Error('Missing ETag in response');
        }
        
        Logger.debug(`Chunk ${partNumber} uploaded (Attempt ${attempt})`);
        return etag;
        
      } catch (error) {
        lastError = error;
        Logger.warn(`Chunk ${partNumber} failed (Attempt ${attempt}):`, error.message);
        
        if (attempt < maxRetries) {
          // Exponential backoff
          const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }
    
    throw lastError;
  }
  
  /**
   * Update upload progress in UI
   */
  updateProgress(caseNumber, documentId, uploadedParts, totalParts) {
    const progress = Math.round((uploadedParts / totalParts) * 100);
    
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: MESSAGE_TYPES.UPDATE_PROGRESS,
          case_number: caseNumber,
          document_id: documentId,
          progress
        }).catch(() => {
          // Tab might be closed, ignore error
        });
      }
    });
  }
}
