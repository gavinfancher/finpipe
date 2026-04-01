import { Link, useParams } from "react-router-dom";
import NavBar from "../components/NavBar";
import MarkdownContent from "../components/MarkdownContent";
import { loadBlogPosts } from "../lib/markdown";

const POSTS = loadBlogPosts();

function PostList() {
  return (
    <div className="blog-list">
      {POSTS.map((post) => (
        <Link to={`/blog/${post.slug}`} key={post.slug} className="blog-card">
          <span className="blog-card__date">{post.date}</span>
          <h2 className="blog-card__title">{post.title}</h2>
          <p className="blog-card__summary">{post.summary}</p>
        </Link>
      ))}
    </div>
  );
}

function PostDetail({ slug }: { slug: string }) {
  const post = POSTS.find((p) => p.slug === slug);

  if (!post) {
    return (
      <div className="blog-empty">
        <p>post not found.</p>
        <Link to="/blog">back to blog</Link>
      </div>
    );
  }

  return (
    <article className="blog-post">
      <Link to="/blog" className="blog-back">&larr; back</Link>
      <h1 className="blog-post__title">{post.title}</h1>
      <span className="blog-post__date">{post.date}</span>
      <MarkdownContent html={post.html} className="blog-post__body" />
    </article>
  );
}

export default function Blog() {
  const { slug } = useParams();

  return (
    <div className="home-page">
      <NavBar />
      <div className="learn-page">
        {slug ? <PostDetail slug={slug} /> : (
          <>
            <h1 className="learn-title">blog</h1>
            <p className="learn-intro">
              engineering decisions, architectural trade-offs, and lessons learned
              building finpipe.
            </p>
            <PostList />
          </>
        )}
      </div>
    </div>
  );
}
