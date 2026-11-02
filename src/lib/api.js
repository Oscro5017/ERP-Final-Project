const tokenKey = 'organic_farm_token';

export function getToken() {
  return localStorage.getItem(tokenKey);
}

export function getRole() {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(payload)).role || null;
  } catch {
    return null;
  }
}

export function clearToken() {
  localStorage.removeItem(tokenKey);
}

export async function api(path, options = {}) {
  const token = getToken();
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (response.status === 401 && path !== '/auth/login' && token) {
    clearToken();
    sessionStorage.setItem('organic_farm_session_expired', '1');
    window.location.assign('/?sessionExpired=1');
    throw new Error('เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่');
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((error) => error.msg).filter(Boolean).join(', ')
      : body.detail;
    throw new Error(detail || 'ไม่สามารถเชื่อมต่อกับระบบได้');
  }

  if (response.status === 204) return null;
  return response.json();
}

export async function login(username, password) {
  const data = await api('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem(tokenKey, data.access_token);
  return data;
}
