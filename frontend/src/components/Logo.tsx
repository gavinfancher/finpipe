export default function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
      <rect width="28" height="28" rx="6" fill="var(--bg-elevated)" stroke="var(--border)" strokeWidth="1"/>
      <text
        x="14" y="19"
        textAnchor="middle"
        fill="var(--accent)"
        fontFamily="'JetBrains Mono', 'Fira Code', monospace"
        fontSize="13"
        fontWeight="700"
      >fp</text>
    </svg>
  );
}
