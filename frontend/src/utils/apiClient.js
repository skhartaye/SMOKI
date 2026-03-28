/**
 * API client with fallback support
 * Tries primary API URL first, then falls back to alternative URL (dev only)
 */

const API_URL = import.meta.env.VITE_API_URL || 'https://smoki-backend.onrender.com';
const API_URL_FALLBACK = import.meta.env.VITE_API_URL_FALLBACK || '';

let currentApiUrl = API_URL;

export const getCurrentApiUrl = () => currentApiUrl;

export const setCurrentApiUrl = (url) => {
  currentApiUrl = url;
};

export const resetApiUrl = () => {
  currentApiUrl = API_URL;
};

/**
 * Fetch with automatic fallback
 * @param {string} endpoint - API endpoint (e.g., '/api/sensors/status')
 * @param {object} options - Fetch options
 * @returns {Promise<Response>}
 */
export const fetchWithFallback = async (endpoint, options = {}) => {
  try {
    const response = await fetch(`${currentApiUrl}${endpoint}`, options);
    
    // If successful, return response
    if (response.ok) {
      return response;
    }
    
    // If not ok and we have a fallback URL and we haven't tried it yet, try it
    if (API_URL_FALLBACK && currentApiUrl !== API_URL_FALLBACK) {
      try {
        const fallbackResponse = await fetch(`${API_URL_FALLBACK}${endpoint}`, options);
        if (fallbackResponse.ok) {
          setCurrentApiUrl(API_URL_FALLBACK);
          return fallbackResponse;
        }
        // Return the original response if fallback also fails
        return response;
      } catch (fallbackErr) {
        // Return original response if fallback throws
        return response;
      }
    }
    
    return response;
  } catch (err) {
    // If primary fails, try fallback (only if we have one)
    if (API_URL_FALLBACK && currentApiUrl !== API_URL_FALLBACK) {
      try {
        const fallbackResponse = await fetch(`${API_URL_FALLBACK}${endpoint}`, options);
        if (fallbackResponse.ok) {
          setCurrentApiUrl(API_URL_FALLBACK);
          return fallbackResponse;
        }
      } catch (fallbackErr) {
        // Both failed, throw original error
      }
    }
    throw err;
  }
};
