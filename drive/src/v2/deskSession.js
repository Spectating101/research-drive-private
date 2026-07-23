const EMAIL_KEY = "procure_user_email";
const TOKEN_KEY = "desk_access_token";
const SESSION_KEY = "rd_v2_chat_session";
const DESK_SESSION_BOOTSTRAPPED_KEY = "rd_desk_session_bootstrapped";

export function deskHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = loadDeskToken();
  if (token) headers["X-Desk-Token"] = token;
  return headers;
}

/** Default fetch init for desk API calls (cookie session + optional pasted token). */
export function deskFetchInit(init = {}) {
  const options = { credentials: "include", ...(init || {}) };
  const headers = deskHeaders(options.headers || {});
  return { ...options, headers };
}

export function loadDeskToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function saveDeskToken(token) {
  const v = String(token || "").trim();
  try {
    if (v) sessionStorage.setItem(TOKEN_KEY, v);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
  return v;
}

export function clearDeskToken() {
  saveDeskToken("");
}

export function hasDeskToken() {
  return Boolean(loadDeskToken());
}

export function markDeskSessionBootstrapped(ok = true) {
  try {
    if (ok) sessionStorage.setItem(DESK_SESSION_BOOTSTRAPPED_KEY, "1");
    else sessionStorage.removeItem(DESK_SESSION_BOOTSTRAPPED_KEY);
  } catch {
    /* ignore */
  }
}

export function deskSessionBootstrapped() {
  try {
    return sessionStorage.getItem(DESK_SESSION_BOOTSTRAPPED_KEY) === "1";
  } catch {
    return false;
  }
}

export function loadUserEmail() {
  try {
    return localStorage.getItem(EMAIL_KEY) || "";
  } catch {
    return "";
  }
}

export function saveUserEmail(email) {
  const v = String(email || "").trim();
  if (v) localStorage.setItem(EMAIL_KEY, v);
  else localStorage.removeItem(EMAIL_KEY);
  return v;
}

export function loadChatSessionId() {
  try {
    return localStorage.getItem(SESSION_KEY) || "";
  } catch {
    return "";
  }
}

export function saveChatSessionId(id) {
  if (!id) return;
  localStorage.setItem(SESSION_KEY, id);
}
