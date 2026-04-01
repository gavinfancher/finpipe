import NavBar from "../components/NavBar";
import MarkdownContent from "../components/MarkdownContent";
import { loadLearnSections } from "../lib/markdown";

const SECTIONS = loadLearnSections();

export default function Learn() {
  return (
    <div className="home-page">
      <NavBar />
      <div className="learn-page">
        <h1 className="learn-title">how finpipe works</h1>
        <p className="learn-intro">
          finpipe is a full-stack market data platform built to ingest, process,
          and serve equity data at scale. here's how the pieces fit together.
        </p>

        <div className="learn-sections">
          {SECTIONS.map((section) => (
            <section key={section.title} className="learn-block">
              <h2>{section.title}</h2>
              <MarkdownContent html={section.html} />
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
