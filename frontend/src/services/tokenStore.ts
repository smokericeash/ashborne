const REFRESH_KEY = "ashborne.refresh_token";

let accessToken: string | null = null;
let refreshToken = safeRead(REFRESH_KEY);

// Access tokens intentionally live only in memory. Remove the key used by early
// development builds without ever reading its value back into the application.
safeWrite("ashborne.access_token", null);

function safeRead(key: string) {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeWrite(key: string, value: string | null) {
  try {
    if (value) window.sessionStorage.setItem(key, value);
    else window.sessionStorage.removeItem(key);
  } catch {
    // Storage may be unavailable in privacy-restricted browser contexts.
  }
}

export const tokenStore = {
  getAccess: () => accessToken,
  getRefresh: () => refreshToken,
  set(access: string, refresh?: string | null) {
    accessToken = access;
    if (refresh !== undefined) {
      refreshToken = refresh;
      safeWrite(REFRESH_KEY, refresh);
    }
  },
  clear() {
    accessToken = null;
    refreshToken = null;
    // Remove the legacy key from pre-0.1 development builds, if present.
    safeWrite("ashborne.access_token", null);
    safeWrite(REFRESH_KEY, null);
  },
};
