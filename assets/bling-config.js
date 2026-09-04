/* Production deployment injects these public, non-secret Firebase values. */
window.BLING_API_BASE = window.BLING_API_BASE || (/^127\.0\.0\.1$|^localhost$/i.test(location.hostname) ? location.origin : 'http://127.0.0.1:8765');
window.BLING_FIREBASE_CONFIG = window.BLING_FIREBASE_CONFIG || null;
