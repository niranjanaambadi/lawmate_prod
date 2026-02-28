// src/utils/constants.js

export const CONFIG = {
  // API Configuration
  API_BASE_URL: 'http://127.0.0.1:8000',
  WEB_BASE_URL: 'http://localhost:3000',
  API_VERSION: 'v1',
  API_TIMEOUT: 30000, // 30 seconds
  
  // Upload Configuration
  CHUNK_SIZE: 5 * 1024 * 1024, // 5MB
  MULTIPART_THRESHOLD: 15 * 1024 * 1024, // 15MB
  MAX_RETRIES: 3,
  CONCURRENT_UPLOADS: 3,
  
  // JWT Configuration
  JWT_REFRESH_BUFFER: 300, // 5 minutes before expiry
  JWT_STORAGE_KEY: 'lawmate_jwt',
  JWT_EXPIRY_KEY: 'jwt_expires_at',
  
  // Sync Configuration
  SYNC_INTERVAL_MINUTES: 30,
  MAX_SYNC_RETRIES: 3,
  
  // Storage Keys
  STORAGE_KEYS: {
    USER_PROFILE: 'user_profile',
    LAST_SYNC: 'last_sync_timestamp',
    SYNC_STATUS: 'sync_status',
    UPLOAD_QUEUE: 'upload_queue'
  },
  
  // API Endpoints
  ENDPOINTS: {
    // Auth
    LOGIN: '/api/v1/auth/login',
    REFRESH: null,
    LOGOUT: '/api/v1/auth/logout',
    
    // Identity
    VERIFY_IDENTITY: '/api/v1/identity/verify',
    
    // Cases
    SYNC_CASES: '/api/v1/sync/cases',
    GET_CASES: '/api/v1/cases',
    GET_CASE: '/api/v1/cases/{id}',
    
    // Documents
    SYNC_DOCUMENTS: '/api/v1/sync/documents',
    
    // Upload
    PRESIGNED_URL: '/api/v1/upload/presigned-url',
    MULTIPART_INIT: '/api/v1/upload/multipart/init',
    MULTIPART_COMPLETE: '/api/v1/upload/multipart/complete',
    MULTIPART_ABORT: '/api/v1/upload/multipart/abort',
    
    // Analysis
    GET_ANALYSIS: '/api/v1/analysis/{case_id}'
  },
  
  // Error Messages
  ERRORS: {
    IDENTITY_MISMATCH: 'You are logged into KHC with a different account. Please log in with the correct account.',
    SESSION_EXPIRED: 'Your Lawmate session has expired. Please log in again.',
    NETWORK_ERROR: 'Network error. Please check your internet connection.',
    SYNC_FAILED: 'Failed to sync cases. Please try again.',
    UPLOAD_FAILED: 'Failed to upload document. Please try again.'
  }
};

export const MESSAGE_TYPES = {
  // Content -> Background
  VERIFY_IDENTITY: 'VERIFY_IDENTITY',
  SYNC_CASES: 'SYNC_CASES',
  LOGIN: 'LOGIN',
  
  // Background -> Content
  UPDATE_STATUS: 'UPDATE_STATUS',
  UPDATE_PROGRESS: 'UPDATE_PROGRESS',
  UPDATE_SYNC_PROGRESS: 'UPDATE_SYNC_PROGRESS',
  SHOW_ERROR: 'SHOW_ERROR',
  TRIGGER_AUTO_SYNC: 'TRIGGER_AUTO_SYNC',
  SYNC_SELECTED_CASE: 'SYNC_SELECTED_CASE'
};

export const SYNC_STATUS = {
  IDLE: 'idle',
  SYNCING: 'syncing',
  SUCCESS: 'success',
  FAILED: 'failed'
};

export const UPLOAD_STATUS = {
  PENDING: 'pending',
  UPLOADING: 'uploading',
  COMPLETED: 'completed',
  FAILED: 'failed'
};
