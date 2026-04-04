import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import NavBar from "../components/NavBar";
import MarkdownContent from "../components/MarkdownContent";
import { loadLearnSections } from "../lib/markdown";

const SECTIONS = loadLearnSections();

const SIDEBAR_ITEMS = [
  { key: "overview", label: "overview" },
  { key: "architecture", label: "architecture" },
];

export default function Learn() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [active, setActive] = useState(
    slug ? "architecture" : "overview"
  );

  // Detail view — render full markdown for a specific section
  if (slug) {
    const section = SECTIONS.find((s) => s.slug === slug);
    if (!section) return null;

    return (
      <div className="home-page">
        <NavBar />
        <div className="learn-layout">
          <aside className="learn-sidebar">
            <div className="learn-sidebar__title">learn</div>
            {SIDEBAR_ITEMS.map((item) => (
              <button
                key={item.key}
                className={`learn-sidebar__item${item.key === "architecture" ? " learn-sidebar__item--active" : ""}`}
                onClick={() => { navigate(item.key === "overview" ? "/learn" : "/learn"); setActive(item.key); }}
              >
                {item.label}
              </button>
            ))}
          </aside>
          <div className="learn-content">
            <button className="learn-back" onClick={() => navigate("/learn")}>
              &larr; back
            </button>
            <section className="learn-block">
              <h2>{section.title}</h2>
              <MarkdownContent html={section.html} />
            </section>
          </div>
        </div>
      </div>
    );
  }

  // Index view — overview or architecture summary cards
  const filtered = SECTIONS.filter((s) => s.category === active);

  return (
    <div className="home-page">
      <NavBar />
      <div className="learn-layout">
        <aside className="learn-sidebar">
          <div className="learn-sidebar__title">learn</div>
          {SIDEBAR_ITEMS.map((item) => (
            <button
              key={item.key}
              className={`learn-sidebar__item${active === item.key ? " learn-sidebar__item--active" : ""}`}
              onClick={() => setActive(item.key)}
            >
              {item.label}
            </button>
          ))}
        </aside>
        <div className="learn-content">
          {active === "overview" ? (
            <div className="learn-sections">
              <p className="learn-intro">
                a self-hosted financial data platform that ingests, processes, and
                serves equity market data in real time.
              </p>
              {filtered.map((section) => (
                <section key={section.slug} className="learn-block">
                  <MarkdownContent html={section.html} />
                </section>
              ))}
            </div>
          ) : (
            <div className="learn-sections">
              <p className="learn-intro">
                deep dives into each layer of the pipeline — streaming, storage,
                orchestration, and infrastructure.
              </p>
              {filtered.map((section) => (
                <Link key={section.slug} to={`/learn/${section.slug}`} className="learn-card">
                  <h3 className="learn-card__title">{section.title}</h3>
                  <p className="learn-card__summary">{section.summary}</p>
                  <span className="learn-card__link">read more &rarr;</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
