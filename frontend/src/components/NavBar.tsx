import { Link, useNavigate, useLocation } from "react-router-dom";
import Logo from "./Logo";
import { getCurrentUsername, clearCurrentUsername, clearToken } from "../store/userStore";
import { useColorMode } from "../hooks/useColorMode";

export default function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = getCurrentUsername();
  const onDashboard = location.pathname === "/dashboard";
  const onHome = location.pathname === "/";
  const { mode, toggle } = useColorMode();

  function handleLogout() {
    clearCurrentUsername();
    clearToken();
    navigate("/");
  }

  return (
    <nav className="site-nav">
      <div className="site-nav__left">
        <Logo />
        <Link to={user ? "/dashboard" : "/"} className="site-nav__brand">finpipe</Link>
      </div>
      <div className="site-nav__links">
        <Link to="/learn" className="nav-link">learn</Link>
        <Link to="/blog" className="nav-link">blog</Link>
        <Link to="/demo" className={onHome ? "btn-primary btn-primary--sm" : "nav-link"}>demo</Link>
      </div>
      <div className="site-nav__right">
        <button className="btn-icon" onClick={toggle} title={mode === "dark" ? "switch to light mode" : "switch to dark mode"}>
          {mode === "dark" ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          )}
        </button>
        {user ? (
          <>
            {!onDashboard && <Link to="/dashboard" className="btn-primary btn-primary--sm">dashboard</Link>}
            <button className="btn-ghost btn-ghost--sm" onClick={handleLogout}>sign out</button>
          </>
        ) : (
          <>
            <Link to="/register" className="btn-ghost btn-ghost--sm">register</Link>
            <Link to="/login" className="btn-primary btn-primary--sm">sign in</Link>
          </>
        )}
      </div>
    </nav>
  );
}
