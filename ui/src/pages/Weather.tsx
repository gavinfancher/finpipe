import { useState, useEffect, useRef, useCallback } from "react";
import NavBar from "../components/NavBar";

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

interface Chat {
  id: string;
  title: string;
  messages: Message[];
}

type Provider = "anthropic" | "openai" | "gemini";

interface WeatherConfig {
  provider: Provider;
  apiKey: string;
  model: string;
}

const PROVIDER_MODELS: Record<Provider, string[]> = {
  anthropic: ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"],
  gemini: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
};

const MODEL_LABELS: Record<string, string> = {
  "claude-sonnet-4-20250514": "Sonnet 4",
  "claude-opus-4-20250514": "Opus 4",
  "claude-haiku-4-5-20251001": "Haiku 4.5",
  "gpt-4o": "GPT-4o",
  "gpt-4o-mini": "GPT-4o mini",
  "gpt-4.1": "GPT-4.1",
  "o4-mini": "o4-mini",
  "gemini-2.5-pro": "Gemini 2.5 Pro",
  "gemini-2.5-flash": "Gemini 2.5 Flash",
  "gemini-2.0-flash": "Gemini 2.0 Flash",
};

const PROVIDER_LABELS: Record<Provider, string> = {
  anthropic: "anthropic",
  openai: "openai",
  gemini: "gemini",
};

const LS_KEY = "weather_config";
const CHATS_KEY = "weather_chats";

function loadConfig(): WeatherConfig {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved) return JSON.parse(saved);
  } catch { /* empty */ }
  return { provider: "anthropic", apiKey: "", model: "claude-sonnet-4-20250514" };
}

function saveConfig(config: WeatherConfig) {
  localStorage.setItem(LS_KEY, JSON.stringify(config));
}

function loadChats(): Chat[] {
  try {
    const saved = localStorage.getItem(CHATS_KEY);
    if (saved) return JSON.parse(saved);
  } catch { /* empty */ }
  return [];
}

function saveChats(chats: Chat[]) {
  localStorage.setItem(CHATS_KEY, JSON.stringify(chats));
}

function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, '<code style="background:var(--bg-elevated);padding:1px 4px;border-radius:3px">$1</code>');
}

function chatTitle(messages: Message[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "new chat";
  const text = first.content.slice(0, 40);
  return text.length < first.content.length ? text + "..." : text;
}

const API = `http://${window.location.hostname}:8081`;

export default function Weather() {
  const [chats, setChats] = useState<Chat[]>(loadChats);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [config, setConfig] = useState<WeatherConfig>(loadConfig);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const activeChat = chats.find((c) => c.id === activeChatId) ?? null;
  const messages = activeChat?.messages ?? [];

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);
  useEffect(() => { inputRef.current?.focus(); }, [activeChatId]);

  function updateConfig(partial: Partial<WeatherConfig>) {
    const next = { ...config, ...partial };
    if (partial.provider && partial.provider !== config.provider) {
      next.model = PROVIDER_MODELS[partial.provider][0];
    }
    setConfig(next);
    saveConfig(next);
  }

  function persistChats(updated: Chat[]) {
    setChats(updated);
    saveChats(updated);
  }

  function updateActiveMessages(updater: (msgs: Message[]) => Message[]) {
    setChats((prev) => {
      const updated = prev.map((c) =>
        c.id === activeChatId ? { ...c, messages: updater(c.messages), title: chatTitle(updater(c.messages)) } : c
      );
      saveChats(updated);
      return updated;
    });
  }

  function startNewChat() {
    setActiveChatId(null);
    setInput("");
  }

  function deleteChat(id: string) {
    const updated = chats.filter((c) => c.id !== id);
    persistChats(updated);
    if (activeChatId === id) setActiveChatId(null);
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
    let chatId = activeChatId;
    let currentMessages: Message[];

    if (!chatId) {
      chatId = crypto.randomUUID();
      const newChat: Chat = { id: chatId, title: text.slice(0, 40), messages: [userMsg] };
      persistChats([newChat, ...chats]);
      setActiveChatId(chatId);
      currentMessages = [userMsg];
    } else {
      currentMessages = [...messages, userMsg];
      setChats((prev) => {
        const updated = prev.map((c) =>
          c.id === chatId ? { ...c, messages: currentMessages } : c
        );
        saveChats(updated);
        return updated;
      });
    }

    setInput("");
    setStreaming(true);

    const assistantMsg: Message = { role: "assistant", content: "", toolCalls: [], streaming: true };
    const withAssistant = [...currentMessages, assistantMsg];
    setChats((prev) => {
      const updated = prev.map((c) =>
        c.id === chatId ? { ...c, messages: withAssistant } : c
      );
      saveChats(updated);
      return updated;
    });

    try {
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(`${API}/api/weather/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: currentMessages.map((m) => ({ role: m.role, content: m.content })),
          provider: config.provider,
          api_key: config.apiKey,
          model: config.model,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.text();
        updateActiveMessages((msgs) => {
          const updated = [...msgs];
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

            const cc = currentContent;
            const ct = [...currentTools];
            setChats((prev) => {
              const updated = prev.map((c) => {
                if (c.id !== chatId) return c;
                const msgs = [...c.messages];
                msgs[msgs.length - 1] = {
                  role: "assistant",
                  content: cc,
                  toolCalls: ct.length > 0 ? ct : undefined,
                  streaming: true,
                };
                return { ...c, messages: msgs };
              });
              saveChats(updated);
              return updated;
            });
          } catch { /* ignore malformed SSE */ }
        }
      }

      updateActiveMessages((msgs) => {
        const updated = [...msgs];
        updated[updated.length - 1] = { ...updated[updated.length - 1], streaming: false };
        return updated;
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        updateActiveMessages((msgs) => {
          const updated = [...msgs];
          updated[updated.length - 1] = {
            role: "assistant",
            content: "connection error — is the server running on :8081?",
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
    <div className="analyst-page weather-scope">
      <NavBar />
      <div className="weather-layout">
        {/* Sidebar */}
        <div className={`weather-sidebar${sidebarOpen ? "" : " weather-sidebar--collapsed"}`}>
          <div className="weather-sidebar__top">
            <button className="weather-sidebar__toggle" onClick={() => setSidebarOpen(!sidebarOpen)} title={sidebarOpen ? "collapse" : "expand"}>
              {sidebarOpen ? "\u2190" : "\u2192"}
            </button>
            {sidebarOpen && (
              <button className="weather-sidebar__new" onClick={startNewChat}>
                + new chat
              </button>
            )}
          </div>
          {sidebarOpen && (
            <>
              <div className="weather-sidebar__list">
                {chats.map((chat) => (
                  <div
                    key={chat.id}
                    className={`weather-sidebar__item${chat.id === activeChatId ? " weather-sidebar__item--active" : ""}`}
                  >
                    <button
                      className="weather-sidebar__item-btn"
                      onClick={() => setActiveChatId(chat.id)}
                    >
                      {chat.title}
                    </button>
                    <button
                      className="weather-sidebar__delete"
                      onClick={(e) => { e.stopPropagation(); deleteChat(chat.id); }}
                      title="delete chat"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <button
                className="weather-sidebar__settings"
                onClick={() => setShowSettings(!showSettings)}
              >
                {hasKey ? (
                  <span className="analyst-provider-dot" />
                ) : (
                  <span className="analyst-provider-dot analyst-provider-dot--missing" />
                )}
                settings
              </button>
            </>
          )}
        </div>

        {/* Main chat area */}
        <div className="analyst-content">
          <div className="analyst-messages">
            {messages.length === 0 && (
              <div className="analyst-welcome">
                <div className="analyst-welcome__icon">~</div>
                <h2 className="analyst-welcome__title">finpipe weather</h2>
                <p className="analyst-welcome__sub">
                  real-time US weather data powered by the National Weather Service.
                  ask about forecasts, alerts, and conditions — backed by structured
                  MCP tool calls.
                </p>

                {!hasKey && (
                  <button
                    className="analyst-example"
                    style={{ borderColor: "var(--weather-accent)", color: "var(--weather-accent)" }}
                    onClick={() => setShowSettings(true)}
                  >
                    configure api key to get started
                  </button>
                )}

                <div className="analyst-welcome__examples">
                  <button className="analyst-example" onClick={() => setInput("what's the weather in San Francisco?")}>
                    weather in San Francisco
                  </button>
                  <button className="analyst-example" onClick={() => setInput("are there any active weather alerts in Florida?")}>
                    alerts in Florida
                  </button>
                  <button className="analyst-example" onClick={() => setInput("compare the forecast for New York City vs Chicago")}>
                    NYC vs Chicago forecast
                  </button>
                  <button className="analyst-example" onClick={() => setInput("what's the forecast for Austin, TX this week?")}>
                    Austin TX this week
                  </button>
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`analyst-msg analyst-msg--${msg.role}`}>
                <div className="analyst-msg__label">
                  {msg.role === "user" ? "you" : "weather"}
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
                    {msg.role === "assistant" ? (
                      <span dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                    ) : (
                      msg.content
                    )}
                    {msg.streaming && <span className="analyst-cursor">|</span>}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="analyst-input-area">
            <div className="analyst-input-wrap">
              <textarea
                ref={inputRef}
                className="analyst-input"
                placeholder={hasKey ? "ask about the weather..." : "configure api key first..."}
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
              <div className="weather-model-picker">
                <button
                  className="weather-model-picker__btn"
                  onClick={() => setShowModelPicker(!showModelPicker)}
                >
                  <span className="weather-model-picker__dot" />
                  {MODEL_LABELS[config.model] || config.model}
                  <span className="weather-model-picker__caret">{showModelPicker ? "\u25B2" : "\u25BC"}</span>
                </button>
                {showModelPicker && (
                  <div className="weather-model-picker__dropdown">
                    {(Object.keys(PROVIDER_LABELS) as Provider[]).map((p) => (
                      <div key={p} className="weather-model-picker__group">
                        <div className="weather-model-picker__group-label">{PROVIDER_LABELS[p]}</div>
                        {PROVIDER_MODELS[p].map((m) => (
                          <button
                            key={m}
                            className={`weather-model-picker__option${config.model === m ? " weather-model-picker__option--active" : ""}`}
                            onClick={() => { updateConfig({ provider: p, model: m }); setShowModelPicker(false); }}
                          >
                            {MODEL_LABELS[m] || m}
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {showSettings && (
            <div className="analyst-settings">
              <div className="analyst-settings__header">
                <span className="analyst-settings__title">weather settings</span>
                <button className="btn-icon" onClick={() => setShowSettings(false)}>✕</button>
              </div>
              <p className="analyst-settings__note">
                your api key is stored locally in your browser and sent
                directly to the server — it is never persisted on the server.
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
            </div>
          )}
        </div>
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
