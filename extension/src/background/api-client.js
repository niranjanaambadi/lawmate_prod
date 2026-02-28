// src/background/api-client.js

import { CONFIG } from '../utils/constants.js';
import { Logger } from '../utils/logger.js';
import { Storage } from '../utils/storage.js';

export class APIClient {
  constructor() {
    this.baseURL = CONFIG.API_BASE_URL;
    this.timeout = CONFIG.API_TIMEOUT;
  }
  
  /**
   * Build full URL
   */
  buildURL(endpoint, params = {}) {
    let url = `${this.baseURL}${endpoint}`;
    
    // Replace path parameters
    Object.keys(params).forEach(key => {
      url = url.replace(`{${key}}`, params[key]);
    });
    
    return url;
  }
  
  /**
   * Make authenticated request
   */
  async request(endpoint, options = {}) {
    const url = this.buildURL(endpoint, options.pathParams);
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };
    
    // Add JWT if available
    const jwt = await Storage.getJWT();
    if (jwt) {
      headers['Authorization'] = `Bearer ${jwt}`;
    }
    
    const fetchOptions = {
      method: options.method || 'GET',
      headers,
      ...options.fetchOptions
    };
    
    if (options.body) {
      fetchOptions.body = JSON.stringify(options.body);
    }
    
    Logger.debug(`API Request: ${options.method || 'GET'} ${url}`, {
      headers: { ...headers, Authorization: jwt ? 'Bearer ***' : undefined }
    });
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeout);
      
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      let data = {};
      if (response.status !== 204) {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          data = await response.json();
        } else {
          const text = await response.text();
          if (text) {
            try {
              data = JSON.parse(text);
            } catch {
              data = { raw: text };
            }
          }
        }
      }
      
      if (!response.ok) {
        throw new APIError(data.detail || 'Request failed', response.status, data);
      }
      
      Logger.debug(`API Response: ${response.status}`, { data });
      
      return data;
      
    } catch (error) {
      if (error.name === 'AbortError') {
        Logger.error('API request timeout', { endpoint });
        throw new APIError('Request timeout', 408);
      }
      
      Logger.error('API request failed', { endpoint, error: error.message });
      throw error;
    }
  }
  
  /**
   * GET request
   */
  async get(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'GET' });
  }
  
  /**
   * POST request
   */
  async post(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'POST', body });
  }
  
  /**
   * PUT request
   */
  async put(endpoint, body, options = {}) {
    return this.request(endpoint, { ...options, method: 'PUT', body });
  }
  
  /**
   * DELETE request
   */
  async delete(endpoint, options = {}) {
    return this.request(endpoint, { ...options, method: 'DELETE' });
  }
}

export class APIError extends Error {
  constructor(message, statusCode, data = {}) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
    this.data = data;
  }
}
