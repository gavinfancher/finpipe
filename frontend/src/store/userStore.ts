export function getCurrentUsername(): string | null {
  return localStorage.getItem("finpipe_user");
}

export function setCurrentUsername(username: string): void {
  localStorage.setItem("finpipe_user", username);
}

export function clearCurrentUsername(): void {
  localStorage.removeItem("finpipe_user");
}

export function getToken(): string | null {
  return localStorage.getItem("finpipe_token");
}

export function setToken(token: string): void {
  localStorage.setItem("finpipe_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("finpipe_token");
}
