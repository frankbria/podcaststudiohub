/**
 * Runtime configuration
 * Uses window.__ENV__ loaded from /config.js at runtime
 * Falls back to build-time env vars for development
 */

declare global {
  interface Window {
    __ENV__?: {
      API_URL: string;
    };
  }
}

export function getConfig() {
  // Runtime config (production)
  if (typeof window !== 'undefined' && window.__ENV__) {
    return {
      apiUrl: window.__ENV__.API_URL,
    };
  }

  // Fallback to build-time env vars (development)
  return {
    apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  };
}

export const config = {
  get apiUrl() {
    return getConfig().apiUrl;
  },
};
