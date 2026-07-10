const EMAIL_KEY = "procure_user_email";
const TOKEN_KEY = "desk_access_token";
const SESSION_KEY = "rd_v2_chat_session";

export function deskHeaders(extra = {}) {
  const headers = { "Content-Type": "application/json", ...extra };
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) headers["X-Desk-Token"] = token;
  return headers;
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
