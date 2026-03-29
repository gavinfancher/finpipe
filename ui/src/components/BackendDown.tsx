import { Link } from "react-router-dom";
import Logo from "./Logo";

export default function BackendDown() {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <Logo />
          <span className="logo-text">finpipe</span>
        </div>
        <p className="login-subtitle">backend unavailable</p>

        <div className="backend-down">
          <p className="backend-down__msg">
            the finpipe api server is temporarily offline.
            this usually means the ec2 instance is stopped to save costs.
          </p>
          <p className="backend-down__msg backend-down__msg--muted">
            the page will reconnect automatically when the server comes back up.
          </p>
        </div>

        <p className="login-back">
          <Link to="/">back to home</Link>
        </p>
      </div>
    </div>
  );
}
