// extension/src/content/dom-parser.js

/**
 * DOM Parser Module for Kerala High Court E-Filing Portal
 * 
 * This module handles parsing of the "My Cases" page and extracting
 * case metadata, party information, and document links.
 * 
 * Version: 1.0.0
 * Last Updated: 2026-01-15
 */

import { Logger } from '../utils/logger.js';

export class KHCDOMParser {
  constructor() {
    // Selectors (may need adjustment based on actual KHC portal structure)
    this.selectors = {
      // Main table
      caseTable: '#mycase-pet-table, #mycase-res-table, #mycase-amicus-table, #myCasesTable, table.cases-table, .case-list-table, table[summary*="cases"]',
      tableBody: 'tbody',
      tableRows: 'tbody tr',
      
      // Header/Identity
      advocateHeader: '.user-profile, .advocate-info, #advocateName, .header-user-info, .user-info',
      advocateIdElement: '.advocate-id, #advocateId, [data-advocate-id]',
      advocateNameElement: '.advocate-name, .name, .user-name, .user-info, .nav-user-photo + .user-info',
      
      // Document links
      pdfLinks: 'a[href*=".pdf"], a[href*="download"], a[href*="document"], a[href*="Casebundle/loadBundle"], a.document-link',
      bundleButtons: 'button[onclick*="PrintCaseBundle"]',
      
      // Case detail modal/popup (if exists)
      caseDetailModal: '.case-detail-modal, #caseDetailPopup'
    };
    
    // Column mappings (0-indexed, adjust based on actual table structure)
    this.columnIndex = {
      // DigiCourt My Cases table:
      // 0 Sl.No, 1 Case No, 2 e-File Details, 3 Pet/Resp, 4 Status, 5 e-File Print, 6 Details
      caseNumber: 1,
      partyNames: 3,
      caseType: 2,
      filingDate: 2,
      nextDate: 2,
      status: 4
    };
  }

  // ============================================================================
  // Main Extraction Methods
  // ============================================================================

  /**
   * Extract logged-in advocate identity from page header
   * @returns {Object|null} - { khc_id, name, scraped_at, page_url }
   */
  extractAdvocateIdentity() {
    Logger.info('Extracting advocate identity from KHC portal');
    
    try {
      // Strategy 1: Look for explicit advocate ID element
      let khcId = this._extractKHCId();
      let name = this._extractAdvocateName();
      
      // Strategy 2: Fallback - Parse from page text
      if (!khcId) {
        const pageText = document.body.innerText;
        
        // Common patterns in Indian court portals
        const patterns = [
          /Advocate\s+ID[:\s]+([A-Z0-9\/\-]+)/i,
          /Enrollment\s+No[:\s]+([A-Z0-9\/\-]+)/i,
          /KHC[\/\-]\w+[\/\-]\d+/,
          /Advocate\s+Code[:\s]+([A-Z0-9\/\-]+)/i
        ];
        
        for (const pattern of patterns) {
          const match = pageText.match(pattern);
          if (match) {
            khcId = match[1] || match[0];
            break;
          }
        }
      }
      
      // Strategy 3: Extract from URL parameters
      if (!khcId) {
        const urlParams = new URLSearchParams(window.location.search);
        khcId = urlParams.get('advocate_id') || urlParams.get('adv_id');
      }
      
      // Fallback for name if selector-based extraction fails
      if (!name) {
        const pageText = document.body.innerText || '';
        const namePatterns = [
          /Welcome[,:\s]+([A-Za-z][A-Za-z\s\.]{2,})/i,
          /Advocate\s*Name[:\s]+([A-Za-z][A-Za-z\s\.]{2,})/i,
          /full_name["']?\s*[:=]\s*["']([A-Za-z][A-Za-z\s\.]{2,})["']/i,
          /name["']?\s*[:=]\s*["']([A-Za-z][A-Za-z\s\.]{2,})["']/i
        ];
        for (const pattern of namePatterns) {
          const match = pageText.match(pattern);
          if (match?.[1]) {
            name = match[1].trim();
            break;
          }
        }
      }

      // Validation (name-based identity handshake)
      if (!name || name.trim().length < 2) {
        Logger.error('Could not extract advocate name from page');
        return null;
      }
      
      const identity = {
        khc_id: khcId ? khcId.trim() : null,
        name: name.trim(),
        scraped_at: new Date().toISOString(),
        page_url: window.location.href,
        user_agent: navigator.userAgent
      };
      
      Logger.info('Advocate identity extracted successfully', identity);
      return identity;
      
    } catch (error) {
      Logger.error('Failed to extract advocate identity', { error: error.message });
      return null;
    }
  }

  /**
   * Parse all cases from the "My Cases" table
   * @returns {Array} - Array of case objects
   */
  parseCaseTable() {
    Logger.info('Parsing case table from KHC portal');
    
    try {
      const table = document.querySelector(this.selectors.caseTable);
      
      if (!table) {
        Logger.error('Case table not found on page', {
          selector: this.selectors.caseTable,
          url: window.location.href
        });
        return [];
      }
      
      // Resolve actual column indexes from table headers to avoid hardcoded drift.
      this.resolveColumnIndex(table);

      const rows = table.querySelectorAll(this.selectors.tableRows);
      Logger.debug(`Found ${rows.length} case rows in table`);
      
      const cases = [];
      
      rows.forEach((row, index) => {
        try {
          const caseData = this.parseCaseRow(row, index);
          if (caseData) {
            cases.push(caseData);
          }
        } catch (error) {
          Logger.error(`Failed to parse row ${index}`, { 
            error: error.message,
            rowHtml: row.outerHTML.substring(0, 200) 
          });
        }
      });
      
      Logger.info(`Successfully parsed ${cases.length} cases`);
      return cases;
      
    } catch (error) {
      Logger.error('Failed to parse case table', { error: error.message });
      return [];
    }
  }

  /**
   * Parse a single case row
   * @param {HTMLTableRowElement} row - The table row element
   * @param {number} rowIndex - Row index for debugging
   * @returns {Object|null} - Case data object
   */
  parseCaseRow(row, rowIndex = 0) {
    const cells = row.querySelectorAll('td');
    
    if (cells.length < 3) {
      Logger.warn('Row has insufficient columns', { 
        rowIndex, 
        columns: cells.length 
      });
      return null;
    }
    
    // Extract all fields
    const caseNumber = this.extractCaseNumber(cells[this.columnIndex.caseNumber]);
    const efilingNumber = this.extractEfilingNumber(row, caseNumber);
    const partyNames = this.extractPartyNames(cells[this.columnIndex.partyNames]);
    const caseType = this.extractCaseType(caseNumber || cells[this.columnIndex.caseType]?.textContent);
    const filingDate = this.extractDate(cells[this.columnIndex.filingDate]);
    const nextDate = this.extractDate(cells[this.columnIndex.nextDate]);
    const status = this.extractStatus(cells[this.columnIndex.status]);
    const partyRole = this.determinePartyRole(row, partyNames);
    const pdfLinks = this.extractPDFLinks(row);
    const benchInfo = this.extractBenchInfo(row);
    
    const caseData = {
      // Case identification
      case_number: caseNumber,
      efiling_number: efilingNumber,
      case_type: caseType,
      case_year: this.extractYear(caseNumber || filingDate),
      
      // Party information
      party_role: partyRole,
      petitioner_name: partyNames.petitioner,
      respondent_name: partyNames.respondent,
      
      // Dates
      efiling_date: filingDate,
      next_hearing_date: nextDate,
      
      // Status and details
      status: status,
      efiling_details: this.extractCaseDetails(row),
      
      // Court information
      bench_type: benchInfo.bench_type,
      judge_name: benchInfo.judge_name,
      court_number: benchInfo.court_number,
      
      // Source
      khc_source_url: window.location.href,
      
      // Documents
      pdf_links: pdfLinks,
      
      // Metadata
      row_index: rowIndex,
      scraped_at: new Date().toISOString()
    };
    
    return caseData;
  }

  // ============================================================================
  // Identity Extraction Helpers
  // ============================================================================

  _extractKHCId() {
    const selectors = [
      '.advocate-id',
      '#advocateId',
      '[data-advocate-id]',
      '.khc-id',
      '.enrollment-number'
    ];
    
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const id = element.getAttribute('data-advocate-id') || 
                   element.textContent.trim();
        
        // Validate format (e.g., KHC/XXX/YYYY)
        if (id && /[A-Z0-9\/\-]+/.test(id)) {
          return id;
        }
      }
    }
    
    return null;
  }

  _extractAdvocateName() {
    const selectors = [
      '.advocate-name',
      '.user-name',
      '#userName',
      '.header-user-info .name',
      '.user-info'
    ];
    
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const text = (element.textContent || '').replace(/\s+/g, ' ').trim();
        if (!text) continue;
        const welcomeMatch = text.match(/Welcome,?\s*(.+)$/i);
        return (welcomeMatch?.[1] || text).trim();
      }
    }
    
    return null;
  }

  // ============================================================================
  // Field Extraction Methods
  // ============================================================================

  /**
   * Extract case number from cell
   * @param {HTMLTableCellElement} cell 
   * @returns {string|null}
   */
  extractCaseNumber(cell) {
    if (!cell) return null;
    
    const text = cell.textContent.trim();
    
    // Prefer Filing No from the Case No column when present (requested app behavior).
    const filingMatch = text.match(/Filing\s*No\.?\s*[:\-]?\s*([A-Z()./\s-]*\d+\s*\/\s*\d{4})/i);
    if (filingMatch?.[1]) {
      return filingMatch[1].replace(/\s+/g, ' ').trim();
    }

    // Common Kerala High Court case number patterns
    const patterns = [
      // WP(C) 123/2026
      /([A-Z]+\([A-Z]\)\s*\d+\/\d{4})/,
      // CRL.A 456/2025
      /([A-Z]+\.\s*[A-Z]+\s*\d+\/\d{4})/,
      // OP 789/2024
      /([A-Z]{2,}\s*\d+\/\d{4})/,
      // WP(C).No.123/2026
      /([A-Z]+\([A-Z]\)\.No\.\d+\/\d{4})/
    ];
    
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        return match[1].trim().replace(/\s+/g, ' ');
      }
    }
    
    // Fallback: Check if cell has a link with case number
    const link = cell.querySelector('a');
    if (link) {
      const linkText = link.textContent.trim();
      for (const pattern of patterns) {
        const match = linkText.match(pattern);
        if (match) return match[1].trim();
      }
    }
    
    // Last resort: preserve visible "Case No / Filing No" text as case number.
    if (text && text !== '-') {
      return text.replace(/\s+/g, ' ').trim();
    }

    return null;
  }

  /**
   * Extract e-filing number
   * @param {HTMLTableRowElement} row 
   * @returns {string}
   */
  extractEfilingNumber(row, fallbackCaseNumber = null) {
    const text = row.textContent.toUpperCase();
    
    // Pattern: EKHC/2026/WPC/00123
    const patterns = [
      /EF-[A-Z]+-\d{4}-\d+/,
      /E[A-Z]{2,}\/\d{4}\/[A-Z]+\/\d+/,
      /EFILE[\/\-]\d{4}[\/\-][A-Z]+[\/\-]\d+/,
      /REG[\/\-]NO[\/\-]\d+[\/\-]\d{4}/
    ];
    
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) return match[0];
    }
    
    // Fallback: use case number when no explicit e-filing number is present.
    if (fallbackCaseNumber) {
      return fallbackCaseNumber;
    }

    // Last resort: Generate temporary ID
    const timestamp = Date.now();
    return `TEMP-EFILE-${timestamp}`;
  }

  /**
   * Resolve column indexes from visible table headers.
   */
  resolveColumnIndex(table) {
    try {
      const headers = Array.from(table.querySelectorAll('thead th')).map((th) =>
        (th.textContent || '').trim().toLowerCase()
      );
      if (!headers.length) return;

      const findIndex = (predicates, fallback) => {
        const idx = headers.findIndex((h) => predicates.some((p) => h.includes(p)));
        return idx >= 0 ? idx : fallback;
      };

      this.columnIndex.caseNumber = findIndex(['case no', 'case number'], this.columnIndex.caseNumber);
      this.columnIndex.partyNames = findIndex(['pet/resp', 'petitioner', 'respondent', 'pet / resp'], this.columnIndex.partyNames);
      this.columnIndex.status = findIndex(['status'], this.columnIndex.status);

      const detailsIdx = findIndex(['e-file details', 'efile details'], this.columnIndex.caseType);
      this.columnIndex.caseType = detailsIdx;
      this.columnIndex.filingDate = detailsIdx;
      this.columnIndex.nextDate = detailsIdx;
    } catch (error) {
      Logger.warn('Failed to resolve table column indexes', { error: error.message });
    }
  }

  /**
   * Extract party names (petitioner vs respondent)
   * @param {HTMLTableCellElement} cell 
   * @returns {Object} - { petitioner, respondent }
   */
  extractPartyNames(cell) {
    if (!cell) {
      return { petitioner: 'Unknown', respondent: 'Unknown' };
    }
    
    let text = cell.textContent.trim();
    
    // Remove extra whitespace
    text = text.replace(/\s+/g, ' ');
    
    // Common separators in Indian court case names
    const separators = [
      ' vs ',
      ' v. ',
      ' Vs. ',
      ' V. ',
      ' versus ',
      ' Versus ',
      ' v/s ',
      ' V/S '
    ];
    
    for (const separator of separators) {
      if (text.toLowerCase().includes(separator.toLowerCase())) {
        const regex = new RegExp(separator, 'i');
        const parts = text.split(regex);
        
        return {
          petitioner: this._cleanPartyName(parts[0]),
          respondent: this._cleanPartyName(parts[1] || 'Not specified')
        };
      }
    }
    
    // Check for line breaks
    if (cell.innerHTML.includes('<br>')) {
      const parts = cell.innerHTML.split(/<br\s*\/?>/i);
      if (parts.length >= 2) {
        return {
          petitioner: this._cleanPartyName(parts[0]),
          respondent: this._cleanPartyName(parts[1])
        };
      }
    }
    
    // Fallback: Check for "and" separator
    if (text.toLowerCase().includes(' and ')) {
      const parts = text.split(/\s+and\s+/i);
      return {
        petitioner: this._cleanPartyName(parts[0]),
        respondent: this._cleanPartyName(parts.slice(1).join(' and '))
      };
    }
    
    // Last resort: Whole text as petitioner
    return {
      petitioner: this._cleanPartyName(text),
      respondent: 'Not specified'
    };
  }

  /**
   * Clean party name (remove HTML, extra spaces)
   * @private
   */
  _cleanPartyName(name) {
    if (!name) return 'Unknown';
    
    // Remove HTML tags
    const div = document.createElement('div');
    div.innerHTML = name;
    let cleaned = div.textContent || div.innerText || '';
    
    // Remove extra whitespace
    cleaned = cleaned.replace(/\s+/g, ' ').trim();
    
    // Remove common prefixes
    cleaned = cleaned.replace(/^(Petitioner|Respondent|Appellant|Defendant)[:\s]*/i, '');
    
    return cleaned || 'Unknown';
  }

  /**
   * Extract case type from case number or cell
   * @param {string} text 
   * @returns {string}
   */
  extractCaseType(text) {
    if (!text) return 'UNKNOWN';

    const raw = text.replace(/\s+/g, ' ').trim();
    const upper = raw.toUpperCase();

    // Preferred: parse prefix before "<number>/<year>" in case number text.
    // Examples: "WP(C) 5896/2026", "MFA (FOREST) 20/2026"
    const casePrefix = upper.match(/^([A-Z][A-Z\.\s\(\)\/\-&]+?)\s+\d+\s*\/\s*\d{4}\b/);
    if (casePrefix?.[1]) {
      const normalized = this._normalizeCaseType(casePrefix[1]);
      if (normalized && normalized.length > 1) return normalized;
    }

    // Fallback: known common patterns
    const patterns = [
      { regex: /WP\s*\(\s*C\s*\)/i, type: 'WP(C)' },
      { regex: /WP\s*\(\s*CRL\.?\s*\)/i, type: 'WP(Crl.)' },
      { regex: /WP\s*\(\s*PIL\s*\)/i, type: 'WP(PIL)' },
      { regex: /OP\s*\(\s*C\s*\)/i, type: 'OP(C)' },
      { regex: /OP\s*\(\s*CRL\.?\s*\)/i, type: 'OP(Crl.)' },
      { regex: /CRL\.?\s*A/i, type: 'CRL.A' },
      { regex: /\bWA\b/i, type: 'WA' },
      { regex: /\bMFA\b/i, type: 'MFA' },
      { regex: /\bRSA\b/i, type: 'RSA' },
      { regex: /\bOP\b/i, type: 'OP' }
    ];

    for (const { regex, type } of patterns) {
      if (regex.test(upper)) return type;
    }

    return 'UNKNOWN';
  }

  _normalizeCaseType(input) {
    if (!input) return 'UNKNOWN';
    let t = input.replace(/\s+/g, ' ').trim();
    t = t.replace(/\s*\.\s*/g, '.');
    t = t.replace(/\(\s+/g, '(').replace(/\s+\)/g, ')');
    t = t.replace(/\s*\/\s*/g, '/');

    const compact = t.toUpperCase().replace(/[\s.]/g, '');
    const aliases = {
      WPC: 'WP(C)',
      WPCRL: 'WP(Crl.)',
      WPPIL: 'WP(PIL)',
      OPC: 'OP(C)',
      OPCRL: 'OP(Crl.)',
      CRLA: 'CRL.A'
    };

    return aliases[compact] || t;
  }

  /**
   * Extract year from case number or date
   * @param {string} text 
   * @returns {number}
   */
  extractYear(text) {
    if (!text) return new Date().getFullYear();
    
    // Look for 4-digit year
    const match = text.match(/\b(20\d{2})\b/);
    return match ? parseInt(match[1]) : new Date().getFullYear();
  }

  /**
   * Extract date from cell
   * @param {HTMLTableCellElement} cell 
   * @returns {string|null} - ISO date string
   */
  extractDate(cell) {
    if (!cell) return null;
    
    const text = cell.textContent.trim();
    if (!text || text === '-' || text.toLowerCase() === 'n/a') {
      return null;
    }
    
    // Try ISO format: YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
      return text.substring(0, 10);
    }
    
    // Try DD/MM/YYYY or DD-MM-YYYY (Indian format)
    const ddmmyyyyMatch = text.match(/(\d{2})[\/\-](\d{2})[\/\-](\d{4})/);
    if (ddmmyyyyMatch) {
      const [, day, month, year] = ddmmyyyyMatch;
      return `${year}-${month}-${day}`;
    }
    
    // Try MM/DD/YYYY (American format)
    const mmddyyyyMatch = text.match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/);
    if (mmddyyyyMatch) {
      const [, month, day, year] = mmddyyyyMatch;
      return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }
    
    // Try to parse with Date object as last resort
    try {
      const date = new Date(text);
      if (!isNaN(date.getTime())) {
        return date.toISOString().substring(0, 10);
      }
    } catch (e) {
      Logger.debug('Could not parse date', { text });
    }
    
    return null;
  }

  /**
   * Extract case status
   * @param {HTMLTableCellElement} cell 
   * @returns {string}
   */
  extractStatus(cell) {
    if (!cell) return 'pending';
    
    const text = cell.textContent.toLowerCase().trim();
    
    // Status mapping
    const statusMap = {
      'disposed': 'disposed',
      'pending': 'pending',
      'registered': 'registered',
      'filed': 'filed',
      'admitted': 'admitted',
      'dismissed': 'disposed',
      'withdrawn': 'withdrawn',
      'transferred': 'transferred',
      'allowed': 'disposed',
      'rejected': 'disposed'
    };
    
    for (const [keyword, status] of Object.entries(statusMap)) {
      if (text.includes(keyword)) {
        return status;
      }
    }
    
    return 'pending';
  }

  /**
   * Determine if advocate is for petitioner or respondent
   * @param {HTMLTableRowElement} row 
   * @param {Object} partyNames 
   * @returns {string} - 'petitioner' or 'respondent'
   */
  determinePartyRole(row, partyNames) {
    const rowText = row.textContent.toLowerCase();
    
    // Look for explicit indicators
    const indicators = {
      respondent: ['respondent side', 'for respondent', 'r/adv', 'respondent\'s advocate'],
      petitioner: ['petitioner side', 'for petitioner', 'p/adv', 'petitioner\'s advocate']
    };
    
    for (const [role, keywords] of Object.entries(indicators)) {
      if (keywords.some(keyword => rowText.includes(keyword))) {
        return role;
      }
    }
    
    // Check for data attributes
    const partyCell = row.querySelector('td[data-party-role]');
    if (partyCell) {
      const role = partyCell.getAttribute('data-party-role').toLowerCase();
      if (role.includes('respondent')) return 'respondent';
      if (role.includes('petitioner')) return 'petitioner';
    }
    
    // Default: Most advocates file cases, so assume petitioner
    return 'petitioner';
  }

  /**
   * Extract bench information
   * @param {HTMLTableRowElement} row 
   * @returns {Object} - { bench_type, judge_name, court_number }
   */
  extractBenchInfo(row) {
    const text = row.textContent;
    
    let bench_type = null;
    let judge_name = null;
    let court_number = null;
    
    // Bench type
    if (text.includes('Division Bench') || text.includes('DB')) {
      bench_type = 'Division Bench';
    } else if (text.includes('Single Bench') || text.includes('SB')) {
      bench_type = 'Single Bench';
    }
    
    // Judge name
    const judgePatterns = [
      /Hon'ble\s+Justice\s+([A-Z][A-Za-z\s\.]+?)(?:\s+and|,|\.|$)/i,
      /Justice\s+([A-Z][A-Za-z\s\.]+?)(?:\s+and|,|\.|$)/i,
      /Hon'ble\s+Mr\.\s*Justice\s+([A-Z][A-Za-z\s\.]+?)(?:\s+and|,|\.|$)/i
    ];
    
    for (const pattern of judgePatterns) {
      const match = text.match(pattern);
      if (match) {
        judge_name = match[1].trim();
        break;
      }
    }
    
    // Court number
    const courtMatch = text.match(/Court\s+(?:No\.|Number)[:\s]*(\d+)/i) ||
                      text.match(/\b(SB-[IVX]+|\d+)\b/);
    if (courtMatch) {
      court_number = courtMatch[1];
    }
    
    return { bench_type, judge_name, court_number };
  }

  /**
   * Extract case details/description
   * @param {HTMLTableRowElement} row 
   * @returns {string|null}
   */
  extractCaseDetails(row) {
    // Look for a details cell or description
    const detailsCell = row.querySelector('td.case-details, td.description');
    if (detailsCell) {
      return detailsCell.textContent.trim().substring(0, 500);
    }
    
    // Fallback: Use second cell text (often contains party names and brief details)
    const cells = row.querySelectorAll('td');
    if (cells.length > 1) {
      return cells[1].textContent.trim().substring(0, 500);
    }
    
    return null;
  }

  /**
   * Extract PDF document links from row
   * @param {HTMLTableRowElement} row 
   * @returns {Array} - Array of { url, document_id, label, category }
   */
  extractPDFLinks(row) {
    const links = [];
    const pdfAnchors = row.querySelectorAll(this.selectors.pdfLinks);
    
    pdfAnchors.forEach((anchor, index) => {
      const url = anchor.href;
      const label = anchor.textContent.trim() || 
                   anchor.title || 
                   anchor.getAttribute('aria-label') || 
                   `Document ${index + 1}`;
      
      // Skip if not a valid URL
      if (!url || url === '#' || url === 'javascript:void(0)') {
        return;
      }
      
      // Determine category from label or URL
      const category = this.categorizeDocument(label, url);
      
      // Extract document ID
      const documentId = this.extractDocumentId(url, label);
      
      links.push({
        url: url,
        document_id: documentId,
        label: label,
        category: category
      });
    });

    // Also capture case bundle buttons rendered as onclick handlers.
    const bundleButtons = row.querySelectorAll(this.selectors.bundleButtons);
    bundleButtons.forEach((button, index) => {
      const onclick = button.getAttribute('onclick') || '';
      const parsed = this.parsePrintCaseBundleOnclick(onclick);
      if (!parsed) return;

      const basePath = typeof window.path === 'string' && window.path
        ? window.path
        : `${window.location.origin}/digicourt/`;
      const normalizedBase = basePath.endsWith('/') ? basePath : `${basePath}/`;
      const bundleUrl = `${normalizedBase}Casebundle/loadBundle?token=${encodeURIComponent(parsed.etype)}&salt=${encodeURIComponent(parsed.efile_id)}&pds=${encodeURIComponent(parsed.pd)}&cnr=${encodeURIComponent(parsed.cino)}&cny=${encodeURIComponent(parsed.ctitle)}`;

      links.push({
        url: bundleUrl,
        document_id: `bundle-${this.hashCode(bundleUrl)}`,
        label: button.textContent.trim() || `Case Bundle ${index + 1}`,
        category: 'case_bundle'
      });
    });

    // Requirement: sync only Case Bundle PDFs (skip e-file print/case file links).
    return links.filter((link) => link.category === 'case_bundle');
  }

  /**
   * Categorize document based on label or URL
   * @param {string} label 
   * @param {string} url 
   * @returns {string}
   */
  categorizeDocument(label, url = '') {
    const text = (label + ' ' + url).toLowerCase();
    
    const categories = {
      case_bundle: ['case bundle', 'loadbundle', 'casebundle/loadbundle'],
      'case_file': ['petition', 'plaint', 'complaint', 'main', 'case file', 'original petition'],
      'affirmation': ['affirmation', 'affidavit', 'sworn statement'],
      'receipt': ['receipt', 'payment', 'challan', 'fee'],
      'annexure': ['annexure', 'exhibit', 'attachment', 'supporting document'],
      'judgment': ['judgment', 'judgement', 'final order'],
      'court_order': ['order', 'interim order', 'direction'],
      'counter_affidavit': ['counter', 'reply', 'response', 'counter affidavit'],
      'vakalatnama': ['vakalatnama', 'vakalat', 'authorization'],
      'notice': ['notice', 'summons']
    };
    
    for (const [category, keywords] of Object.entries(categories)) {
      if (keywords.some(keyword => text.includes(keyword))) {
        return category;
      }
    }
    
    return 'other';
  }

  /**
   * Parse PrintCaseBundle("etype","efile_id","pd","cino","ctitle") call.
   * @param {string} onclick
   * @returns {Object|null}
   */
  parsePrintCaseBundleOnclick(onclick) {
    if (!onclick || !onclick.includes('PrintCaseBundle')) {
      return null;
    }

    const match = onclick.match(/PrintCaseBundle\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)/);
    if (!match) {
      return null;
    }

    const [, etype, efile_id, pd, cino, ctitle] = match;
    return { etype, efile_id, pd, cino, ctitle };
  }

  /**
   * Extract document ID from URL
   * @param {string} url 
   * @param {string} label 
   * @returns {string}
   */
  extractDocumentId(url, label) {
    // Try to extract from query params
    const urlObj = new URL(url, window.location.origin);
    const params = urlObj.searchParams;
    
    const idParams = ['doc_id', 'document_id', 'file_id', 'id'];
    for (const param of idParams) {
      const value = params.get(param);
      if (value) return value;
    }
    
    // Try to extract from path
    const pathMatch = url.match(/\/documents?\/(\d+)/i) ||
                     url.match(/\/files?\/(\d+)/i) ||
                     url.match(/\/(\d{6,})\./);
    
    if (pathMatch) {
      return pathMatch[1];
    }
    
    // Generate hash-based ID
    return this.hashCode(url + label).toString();
  }

  /**
   * Generate hash code from string
   * @param {string} str 
   * @returns {number}
   */
  hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  }

  // ============================================================================
  // Validation Methods
  // ============================================================================

  /**
   * Validate extracted case data
   * @param {Object} caseData 
   * @returns {boolean}
   */
  validateCaseData(caseData) {
    // Required fields
    const required = ['efiling_number', 'case_type', 'petitioner_name', 'respondent_name'];
    
    for (const field of required) {
      if (!caseData[field] || caseData[field] === 'Unknown') {
        Logger.warn('Missing required field in case data', { 
          field, 
          efiling_number: caseData.efiling_number 
        });
        return false;
      }
    }
    
    return true;
  }

  /**
   * Sanitize case data before sending to backend
   * @param {Object} caseData 
   * @returns {Object}
   */
  sanitizeCaseData(caseData) {
    // Remove HTML entities
    const sanitize = (str) => {
      if (typeof str !== 'string') return str;
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'");
    };
    
    const sanitized = { ...caseData };
    
    // Sanitize string fields
    const stringFields = [
      'case_number', 'efiling_number', 'petitioner_name', 
      'respondent_name', 'efiling_details', 'judge_name'
    ];
    
    for (const field of stringFields) {
      if (sanitized[field]) {
        sanitized[field] = sanitize(sanitized[field]);
      }
    }
    
    return sanitized;
  }
}

// Export singleton instance
export const khcParser = new KHCDOMParser();



// 
// Configuration for Different Portal Versions
// If KHC portal structure varies, you can customize selectors:
// javascriptCopy// Custom configuration
// parser.selectors.caseTable = 'table#customTableId';
// parser.columnIndex.caseNumber = 1; // If case number is in 2nd column

// // Or create a new instance with custom config
// const customParser = new KHCDOMParser();
// customParser.selectors = {
//   ...customParser.selectors,
//   caseTable: 'div.case-container table'
// };
