// src/utils/logger.js

export class Logger {
  static LOG_LEVELS = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3
  };
  
  static currentLevel = Logger.LOG_LEVELS.INFO;
  
  static setLevel(level) {
    Logger.currentLevel = Logger.LOG_LEVELS[level] || Logger.LOG_LEVELS.INFO;
  }
  
  static _log(level, message, data = {}) {
    if (Logger.LOG_LEVELS[level] < Logger.currentLevel) return;
    
    const timestamp = new Date().toISOString();
    const logEntry = {
      timestamp,
      level,
      message,
      ...data
    };
    
    const logMethod = level === 'ERROR' ? 'error' : 
                     level === 'WARN' ? 'warn' : 'log';
    
    console[logMethod](`[Lawmate ${level}] ${timestamp}:`, message, data);
    
    // Store in chrome.storage for debugging
    this._persistLog(logEntry);
  }
  
  static async _persistLog(logEntry) {
    try {
      const { logs = [] } = await chrome.storage.local.get('logs');
      logs.push(logEntry);
      
      // Keep only last 100 logs
      if (logs.length > 100) {
        logs.shift();
      }
      
      await chrome.storage.local.set({ logs });
    } catch (e) {
      console.error('Failed to persist log:', e);
    }
  }
  
  static debug(message, data) {
    this._log('DEBUG', message, data);
  }
  
  static info(message, data) {
    this._log('INFO', message, data);
  }
  
  static warn(message, data) {
    this._log('WARN', message, data);
  }
  
  static error(message, data) {
    this._log('ERROR', message, data);
  }
}