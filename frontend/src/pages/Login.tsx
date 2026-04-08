import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { setCurrentUsername, setToken } from "../store/userStore";
import Logo from "../components/Logo";
import BackendDown from "../components/BackendDown";
import { API_BASE } from "../config";
import { useBackendStatus } from "../hooks/useBackendStatus";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const backend = useBackendStatus();

  if (backend === "down") return <BackendDown />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) return;

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/external/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "something went wrong.");
        return;
      }
      setCurrentUsername(username.trim().toLowerCase());
      setToken(data.access_token);
      navigate("/dashboard");
    } catch {
      setError("could not reach server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <Logo />
          <span className="logo-text">finpipe</span>
        </div>
        <p className="login-subtitle">sign in to your account</p>

        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="username" className="field-label">username</label>
          <input
            id="username"
            type="text"
            className="text-input"
            placeholder="e.g. trader_joe"
            value={username}
            onChange={(e) => { setUsername(e.target.value); setError(""); }}
            autoFocus
            autoComplete="off"
          />

          <label htmlFor="password" className="field-label">password</label>
          <input
            id="password"
            type="password"
            className="text-input"
            placeholder="••••••••"
            value={password}
            onChange={(e) => { setPassword(e.target.value); setError(""); }}
            autoComplete="off"
          />

          {error && <p className="field-error">{error}</p>}

          <button type="submit" className="btn-primary" style={{ width: "100%", marginTop: 4 }} disabled={loading}>
            {loading ? "..." : "sign in"}
          </button>
        </form>

        <p className="login-back">
          need an account? <Link to="/register">request access</Link>
        </p>
        <p className="login-back">
          <Link to="/">back to home</Link>
        </p>
      </div>
    </div>
  );
}
