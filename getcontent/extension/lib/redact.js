// URL and text sanitization utility for safe logging
// Removes sensitive information from URLs and text content

/**
 * Remove sensitive query parameters from URL for safe logging
 * @param {string} input - Input URL
 * @returns {string} - Sanitized URL with only protocol, host, and pathname
 */
export function redactUrl(input) {
  try {
    const u = new URL(input);
    // Only keep protocol, host, and pathname - remove search params and hash
    return `${u.protocol}//${u.host}${u.pathname}`;
  } catch {
    return input;
  }
}

/**
 * Remove sensitive patterns from text content
 * @param {string} s - Input text
 * @returns {string} - Sanitized text with sensitive patterns replaced
 */
export function redactText(s = "") {
  return s
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[email]")
    .replace(/\+?\d[\d\s\-]{6,}\d/g, "[phone]")
    .replace(/[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+/g, "[jwt]")
    .replace(/(?:Bearer|Token)\s+[A-Za-z0-9-_=]+/gi, "[token]")
    .replace(/(?:password|pwd|pass)\s*[:=]\s*[^\s&]+/gi, "password=[redacted]")
    .replace(/(?:api_key|apikey|key)\s*[:=]\s*[^\s&]+/gi, "api_key=[redacted]");
}

/**
 * Create safe page context for logging
 * @param {string} url - Page URL
 * @param {string} title - Page title
 * @returns {object} - Safe page context
 */
export function createPageContext(url, title) {
  return {
    url: redactUrl(url),
    title: redactText(title),
    host: new URL(url).hostname
  };
}