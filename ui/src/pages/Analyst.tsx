import { useState, useEffect, useRef, useCallback } from "react";
import NavBar from "../components/NavBar";
import { getToken } from "../store/userStore";

interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  result?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  streaming?: boolean;
}

type Provider = "anthropic" | "openai" | "gemini";

interface ProviderConfig {
  provider: Provider;
  apiKey: string;
  model: string;
}

const PROVIDER_MODELS: Record<Provider, string[]> = {
  anthropic: ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"],
  gemini: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
};

const PROVIDER_LABELS: Record<Provider, string> = {
  anthropic: "anthropic (claude)",
  openai: "openai",
  gemini: "google gemini",
};

const LS_KEY = "analyst_provider_config";

function loadConfig(): ProviderConfig {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved) return JSON.parse(saved);
  } catch { /* empty */ }
  return { provider: "anthropic", apiKey: "", model: "claude-sonnet-4-20250514" };
}

function saveConfig(config: ProviderConfig) {
  localStorage.setItem(LS_KEY, JSON.stringify(config));
}

const API = `http://${window.location.hostname}:8081`;

export default function Analyst() {
  const token = getToken();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [config, setConfig] = useState<ProviderConfig>(loadConfig);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);
  useEffect(() => { inputRef.current?.focus(); }, []);

  function updateConfig(partial: Partial<ProviderConfig>) {
    const next = { ...config, ...partial };
    if (partial.provider && partial.provider !== config.provider) {
      next.model = PROVIDER_MODELS[partial.provider][0];
    }
    setConfig(next);
    saveConfig(next);
  }

  const hasKey = config.apiKey.trim().length > 0;

  async function handleSubmit() {
    const text = input.trim();
    if (!text || streaming) return;

    if (!hasKey) {
      setShowSettings(true);
      return;
    }

    const userMsg: Message = { role: "user", content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput("");
    setStreaming(true);

    const assistantMsg: Message = { role: "assistant", content: "", toolCalls: [], streaming: true };
    setMessages([...history, assistantMsg]);

    try {
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          messages: history.map((m) => ({ role: m.role, content: m.content })),
          provider: config.provider,
          api_key: config.apiKey,
          model: config.model,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.text();
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `error: ${err}`, streaming: false };
          return updated;
        });
        setStreaming(false);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentContent = "";
      let currentTools: ToolCall[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") continue;

          try {
            const event = JSON.parse(data);
            if (event.type === "text_delta") {
              currentContent += event.text;
            } else if (event.type === "tool_call_start") {
              currentTools = [...currentTools, { name: event.name, input: event.input }];
            } else if (event.type === "tool_call_result") {
              currentTools = currentTools.map((tc, i) =>
                i === currentTools.length - 1 ? { ...tc, result: event.result } : tc
              );
            } else if (event.type === "error") {
              currentContent += `\n[error: ${event.message}]`;
            }

            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: currentContent,
                toolCalls: currentTools.length > 0 ? [...currentTools] : undefined,
                streaming: true,
              };
              return updated;
            });
          } catch { /* ignore malformed SSE */ }
        }
      }

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { ...updated[updated.length - 1], streaming: false };
        return updated;
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: "connection error — is the analyst server running on :8081?",
            streaming: false,
          };
          return updated;
        });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
  }

  function handleStop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  return (
    <div className="analyst-page">
      <NavBar />
      <div className="analyst-content">
        <div className="analyst-messages">
          {messages.length === 0 && (
            <div className="analyst-welcome">
              <div className="analyst-welcome__icon">&gt;_</div>
              <h2 className="analyst-welcome__title">finpipe analyst</h2>
              <p className="analyst-welcome__sub">
                ask questions about your market data. the analyst has access to
                your icehouse lakehouse — minute-level aggregates, session data,
                and rolling metrics.
              </p>

              {!hasKey && (
                <button
                  className="analyst-example"
                  style={{ borderColor: "var(--analyst-accent)", color: "var(--analyst-accent)" }}
                  onClick={() => setShowSettings(true)}
                >
                  configure api key to get started
                </button>
              )}

              <div className="analyst-welcome__examples">
                <button className="analyst-example" onClick={() => setInput("what tickers are available in the silver layer?")}>
                  what tickers are available?
                </button>
                <button className="analyst-example" onClick={() => setInput("show me SPY's average volume by session over the last 5 days")}>
                  SPY volume by session
                </button>
                <button className="analyst-example" onClick={() => setInput("compare AAPL and MSFT closing prices from last week")}>
                  compare AAPL vs MSFT
                </button>
                <button className="analyst-example" onClick={() => setInput("what's the most active ticker by transaction count today?")}>
                  most active ticker today
                </button>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`analyst-msg analyst-msg--${msg.role}`}>
              <div className="analyst-msg__label">
                {msg.role === "user" ? "you" : "analyst"}
              </div>
              <div className="analyst-msg__body">
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="analyst-tools">
                    {msg.toolCalls.map((tc, j) => (
                      <ToolCallBlock key={j} tool={tc} />
                    ))}
                  </div>
                )}
                <div className="analyst-msg__text">
                  {msg.content}
                  {msg.streaming && <span className="analyst-cursor">|</span>}
                </div>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="analyst-input-area">
          <div className="analyst-input-wrap">
            <span className="analyst-prompt">&gt;</span>
            <textarea
              ref={inputRef}
              className="analyst-input"
              placeholder={hasKey ? "ask the analyst..." : "configure api key first..."}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={streaming}
            />
            {streaming ? (
              <button className="analyst-send analyst-send--stop" onClick={handleStop}>stop</button>
            ) : (
              <button className="analyst-send" onClick={handleSubmit} disabled={!input.trim() && hasKey}>send</button>
            )}
            <button
              className="analyst-settings-btn"
              onClick={() => setShowSettings(!showSettings)}
              title="provider settings"
            >
              {hasKey ? (
                <span className="analyst-provider-dot" />
              ) : (
                <span className="analyst-provider-dot analyst-provider-dot--missing" />
              )}
              {config.provider === "anthropic" ? "claude" : config.provider}
            </button>
          </div>
          <div className="analyst-input-hint">
            enter to send · shift+enter for newline · {config.model}
          </div>
        </div>

        {showSettings && (
          <div className="analyst-settings">
            <div className="analyst-settings__header">
              <span className="analyst-settings__title">provider settings</span>
              <button className="btn-icon" onClick={() => setShowSettings(false)}>✕</button>
            </div>
            <p className="analyst-settings__note">
              your api key is stored locally in your browser and sent directly to the
              analyst server — it is never stored on the server.
            </p>

            <label className="field-label">provider</label>
            <div className="analyst-provider-tabs">
              {(Object.keys(PROVIDER_LABELS) as Provider[]).map((p) => (
                <button
                  key={p}
                  className={`analyst-provider-tab${config.provider === p ? " analyst-provider-tab--active" : ""}`}
                  onClick={() => updateConfig({ provider: p })}
                >
                  {PROVIDER_LABELS[p]}
                </button>
              ))}
            </div>

            <label className="field-label">api key</label>
            <input
              type="password"
              className="text-input"
              placeholder={
                config.provider === "anthropic" ? "sk-ant-..." :
                config.provider === "openai" ? "sk-..." : "AIza..."
              }
              value={config.apiKey}
              onChange={(e) => updateConfig({ apiKey: e.target.value })}
              style={{ letterSpacing: config.apiKey ? "0.2em" : "normal", fontSize: config.apiKey ? "16px" : "13px" }}
            />

            <label className="field-label">model</label>
            <div className="analyst-model-list">
              {PROVIDER_MODELS[config.provider].map((m) => (
                <button
                  key={m}
                  className={`analyst-model-btn${config.model === m ? " analyst-model-btn--active" : ""}`}
                  onClick={() => updateConfig({ model: m })}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ToolCallBlock({ tool }: { tool: ToolCall }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="tool-call">
      <button className="tool-call__header" onClick={() => setExpanded(!expanded)}>
        <span className="tool-call__icon">{expanded ? "v" : ">"}</span>
        <span className="tool-call__name">{tool.name}</span>
        {tool.result ? (
          <span className="tool-call__status tool-call__status--done">done</span>
        ) : (
          <span className="tool-call__status tool-call__status--running">running...</span>
        )}
      </button>
      {expanded && (
        <div className="tool-call__body">
          <div className="tool-call__section">
            <div className="tool-call__section-label">input</div>
            <pre className="tool-call__pre">{JSON.stringify(tool.input, null, 2)}</pre>
          </div>
          {tool.result && (
            <div className="tool-call__section">
              <div className="tool-call__section-label">result</div>
              <pre className="tool-call__pre">{tool.result}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
