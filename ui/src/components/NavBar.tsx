import { Link, useLocation, useNavigate } from "react-router-dom";
import Logo from "./Logo";
import { getCurrentUsername, clearCurrentUsername, clearToken } from "../store/userStore";
import { EDITION } from "../config/edition";
import { featureEnabled } from "../config/gates";

export default function NavBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const user = getCurrentUsername();

  function isActive(path: string) {
    return location.pathname.startsWith(path) ? " site-nav__link--active" : "";
  }

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
        <span className="edition-badge">{EDITION}</span>
      </div>
      <div className="site-nav__links">
        <Link to="/dashboard" className={`site-nav__link${isActive("/dashboard")}`}>dashboard</Link>
        <Link to="/faucet" className={`site-nav__link${isActive("/faucet")}`}>faucet</Link>
        <Link to="/icehouse" className={`site-nav__link${isActive("/icehouse")}`}>icehouse</Link>
        <Link to="/analyst" className={`site-nav__link${isActive("/analyst")}`}>analyst</Link>
        <Link to="/undercurrent" className={`site-nav__link${isActive("/undercurrent")}`}>undercurrent</Link>
        <Link to="/weather" className={`site-nav__link${isActive("/weather")}`}>weather</Link>
        {featureEnabled("admin") && (
          <Link to="/admin" className={`site-nav__link${isActive("/admin")}`}>admin</Link>
        )}
      </div>
      <div className="site-nav__right">
        {user ? (
          <>
            <span className="username-badge">{user}</span>
            <button className="btn-ghost btn-ghost--sm" onClick={handleLogout}>sign out</button>
          </>
        ) : (
          <Link to="/login" className="btn-ghost btn-ghost--sm">sign in</Link>
        )}
      </div>
    </nav>
  );
}
