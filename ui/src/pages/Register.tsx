import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { setCurrentUsername, setToken } from "../store/userStore";
import Logo from "../components/Logo";
import BackendDown from "../components/BackendDown";
import { API_BASE } from "../config";
import { useBackendStatus } from "../hooks/useBackendStatus";

export default function Register() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [betaKey, setBetaKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const backend = useBackendStatus();

  if (backend === "down") return <BackendDown />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(username)) {
      setError("only letters, numbers, underscores, and hyphens (max 32 chars).");
      return;
    }
    if (password.length < 6) {
      setError("password must be at least 6 characters.");
      return;
    }
    if (password !== confirm) {
      setError("passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/external/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim().toLowerCase(),
          password,
          beta_key: betaKey.trim(),
        }),
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
        <p className="login-subtitle">create an account</p>

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

          <label htmlFor="confirm" className="field-label">confirm password</label>
          <input
            id="confirm"
            type="password"
            className="text-input"
            placeholder="••••••••"
            value={confirm}
            onChange={(e) => { setConfirm(e.target.value); setError(""); }}
            autoComplete="off"
          />

          <label htmlFor="betaKey" className="field-label">beta key</label>
          <input
            id="betaKey"
            type="text"
            className="text-input"
            placeholder="enter beta key"
            value={betaKey}
            onChange={(e) => { setBetaKey(e.target.value); setError(""); }}
            autoComplete="off"
          />

          {error && <p className="field-error">{error}</p>}

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? "..." : "create account"}
          </button>
        </form>

        <p className="login-back">
          already have an account? <Link to="/login">sign in</Link>
        </p>
        <p className="login-back">
          <Link to="/">back to home</Link>
        </p>
      </div>
    </div>
  );
}
