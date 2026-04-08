import { Link, useNavigate } from "react-router-dom";
import NavBar from "../components/NavBar";
import { getCurrentUsername, getToken } from "../store/userStore";
import { useEffect } from "react";

export default function Dashboard() {
  const navigate = useNavigate();
  const user = getCurrentUsername();
  const token = getToken();

  useEffect(() => {
    if (!user || !token) navigate("/login");
  }, [user, token, navigate]);

  if (!user) return null;

  return (
    <div className="dash-page">
      <NavBar />
      <div className="dash-content">
        <div className="dash-header">
          <h1 className="dash-header__greeting">welcome back, <span className="dash-header__user">{user}</span></h1>
          <p className="dash-header__sub">your finpipe workspace</p>
        </div>

        <div className="dash-grid">
          <Link to="/stream" className="dash-card">
            <div className="dash-card__top">
              <svg className="dash-card__icon-svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
              </svg>
              <span className="dash-card__name">stream</span>
            </div>
            <p className="dash-card__desc">
              real-time streaming dashboard. watchlists, positions, and live p/l.
            </p>
            <div className="dash-card__footer">
              <span className="dash-card__tag">live data</span>
              <span className="dash-card__tag">websocket</span>
            </div>
          </Link>

          <Link to="/account" className="dash-card">
            <div className="dash-card__top">
              <span className="dash-card__icon">@</span>
              <span className="dash-card__name">account</span>
            </div>
            <p className="dash-card__desc">
              manage your profile and api keys.
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}
