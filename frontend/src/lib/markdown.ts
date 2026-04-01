import { marked } from "marked";

export interface PostMeta {
  slug: string;
  title: string;
  date: string;
  summary: string;
  html: string;
}

export interface LearnSection {
  title: string;
  order: number;
  html: string;
}

function parseFrontmatter(raw: string): { meta: Record<string, string>; body: string } {
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return { meta: {}, body: raw };

  const meta: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const idx = line.indexOf(":");
    if (idx > 0) {
      meta[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    }
  }
  return { meta, body: match[2] };
}

export function loadBlogPosts(): PostMeta[] {
  const modules = import.meta.glob("/content/blog/*.md", { eager: true, query: "?raw", import: "default" });

  const posts: PostMeta[] = Object.entries(modules).map(([path, raw]) => {
    const { meta, body } = parseFrontmatter(raw as string);
    const slug = path.replace("/content/blog/", "").replace(".md", "");
    return {
      slug,
      title: meta.title || slug,
      date: meta.date || "",
      summary: meta.summary || "",
      html: marked.parse(body) as string,
    };
  });

  return posts.sort((a, b) => b.date.localeCompare(a.date));
}

export function loadLearnSections(): LearnSection[] {
  const modules = import.meta.glob("/content/learn/*.md", { eager: true, query: "?raw", import: "default" });

  const sections: LearnSection[] = Object.entries(modules).map(([_, raw]) => {
    const { meta, body } = parseFrontmatter(raw as string);
    return {
      title: meta.title || "",
      order: parseInt(meta.order || "99", 10),
      html: marked.parse(body) as string,
    };
  });

  return sections.sort((a, b) => a.order - b.order);
}
