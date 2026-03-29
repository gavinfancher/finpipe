import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import NavBar from "../components/NavBar";
import { getCurrentUsername, getToken } from "../store/userStore";

const API = `http://${window.location.hostname}:8080`;

export default function Account() {
  const navigate = useNavigate();
  const user = getCurrentUsername();
  const token = getToken();

  const [apiKey, setApiKey] = useState<string | null>(null);
  const [apiKeyLoading, setApiKeyLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!user || !token) navigate("/login");
  }, [user, token, navigate]);

  if (!user) return null;

  const authHeader = { Authorization: `Bearer ${token}` };

  async function generateApiKey() {
    setApiKeyLoading(true);
    try {
      const res = await fetch(`${API}/external/api-key`, { method: "POST", headers: authHeader });
      const data = await res.json();
      setApiKey(data.api_key ?? null);
    } finally { setApiKeyLoading(false); }
  }

  function copyKey() {
    if (!apiKey) return;
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="dash-page">
      <NavBar />
      <div className="dash-content">
        <div className="dash-header">
          <h1 className="dash-header__greeting">account</h1>
          <p className="dash-header__sub">manage your finpipe account</p>
        </div>

        <div className="account-sections">
          <div className="account-card">
            <h2 className="account-card__title">profile</h2>
            <div className="account-field">
              <span className="account-field__label">username</span>
              <span className="account-field__value">{user}</span>
            </div>
          </div>

          <div className="account-card">
            <h2 className="account-card__title">api key</h2>
            <p className="account-card__desc">
              generate an api key to interact with finpipe programmatically.
              generating a new key invalidates the previous one.
            </p>
            {apiKey ? (
              <div className="apikey-display">
                <code className="apikey-value">{apiKey}</code>
                <button className="btn-ghost btn-ghost--sm" onClick={copyKey}>
                  {copied ? "copied!" : "copy"}
                </button>
              </div>
            ) : (
              <button className="btn-primary" onClick={generateApiKey} disabled={apiKeyLoading}>
                {apiKeyLoading ? "generating..." : "generate key"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
