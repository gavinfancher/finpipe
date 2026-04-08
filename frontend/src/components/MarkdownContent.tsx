import { useMemo } from "react";
import DOMPurify from "dompurify";
import Mermaid from "./Mermaid";

interface Props {
  html: string;
  className?: string;
}

interface ContentBlock {
  type: "html" | "mermaid";
  content: string;
}

function splitMermaidBlocks(html: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  const regex = /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(html)) !== null) {
    if (match.index > lastIndex) {
      blocks.push({ type: "html", content: html.slice(lastIndex, match.index) });
    }
    // Decode HTML entities back to plain text for mermaid
    const chart = match[1]
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"');
    blocks.push({ type: "mermaid", content: chart });
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < html.length) {
    blocks.push({ type: "html", content: html.slice(lastIndex) });
  }

  return blocks;
}

export default function MarkdownContent({ html, className = "" }: Props) {
  const blocks = useMemo(() => {
    const safe = DOMPurify.sanitize(html);
    return splitMermaidBlocks(safe);
  }, [html]);

  return (
    <div className={className}>
      {blocks.map((block, i) =>
        block.type === "mermaid" ? (
          <Mermaid key={i} chart={block.content} />
        ) : (
          <div key={i} dangerouslySetInnerHTML={{ __html: block.content }} />
        )
      )}
    </div>
  );
}
