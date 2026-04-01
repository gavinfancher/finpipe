import { useEffect, useRef } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    primaryColor: "#1c1c1c",
    primaryTextColor: "#f0f0f0",
    primaryBorderColor: "#2a2a2a",
    lineColor: "#ff9e18",
    secondaryColor: "#141414",
    tertiaryColor: "#0d0d0d",
    fontFamily: "JetBrains Mono, monospace",
    fontSize: "12px",
  },
});

export default function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
    mermaid.render(id, chart).then(({ svg }) => {
      if (ref.current) ref.current.innerHTML = svg;
    });
  }, [chart]);

  return <div ref={ref} className="mermaid-diagram" />;
}
