interface Props {
  variant?: "default" | "faucet" | "ice" | "analyst" | "undercurrent";
}

const COLORS = {
  default: "#6ec8e8",
  faucet: "#6ee86e",
  ice: "#8bb8e8",
  analyst: "#e8c86e",
  undercurrent: "#e86e9a",
};

const LABELS = {
  default: "fp",
  faucet: "f2",
  ice: "ih",
  analyst: ">_",
  undercurrent: "%",
};

export default function Logo({ variant = "default" }: Props) {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
      <rect width="28" height="28" rx="5" fill="#383838"/>
      <text
        x="14" y="19"
        textAnchor="middle"
        fill={COLORS[variant]}
        fontFamily="'JetBrains Mono', 'Fira Code', monospace"
        fontSize="13"
        fontWeight="700"
      >{LABELS[variant]}</text>
    </svg>
  );
}
