import { Link, useNavigate, useLocation } from "react-router-dom";
import Logo from "./Logo";
import { getCurrentUsername, clearCurrentUsername, clearToken } from "../store/userStore";

export default function NavBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = getCurrentUsername();
  const onDashboard = location.pathname === "/dashboard";
  const onHome = location.pathname === "/";

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
        <Link to="/learn" className="btn-ghost btn-ghost--sm">learn</Link>
        <Link to="/blog" className="btn-ghost btn-ghost--sm">blog</Link>
        <Link to="/demo" className={onHome ? "btn-primary btn-primary--sm" : "btn-ghost btn-ghost--sm"}>demo</Link>
      </div>
      <div className="site-nav__right">
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
