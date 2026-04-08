import { useEffect, useRef } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    primaryColor: "#191a1e",
    primaryTextColor: "#d4d4d8",
    primaryBorderColor: "#232329",
    lineColor: "#4a7c59",
    secondaryColor: "#111113",
    tertiaryColor: "#09090b",
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
