import { useEffect, useRef } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

const mdComponents = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: "#3b82f6" }}>
      {children}
    </a>
  ),
  code: ({ inline, children }) =>
    inline ? (
      <code
        style={{
          background: "rgba(0,0,0,0.08)",
          padding: "1px 5px",
          borderRadius: 3,
          fontFamily: "monospace",
          fontSize: "0.9em",
        }}
      >
        {children}
      </code>
    ) : (
      <pre
        style={{
          background: "rgba(0,0,0,0.06)",
          padding: "10px 12px",
          borderRadius: 6,
          overflowX: "auto",
          fontFamily: "monospace",
          fontSize: 12,
          margin: "6px 0",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        <code>{children}</code>
      </pre>
    ),
  h1: ({ children }) => <div style={{ fontWeight: 700, fontSize: 15, margin: "8px 0 4px" }}>{children}</div>,
  h2: ({ children }) => <div style={{ fontWeight: 700, fontSize: 14, margin: "6px 0 3px" }}>{children}</div>,
  h3: ({ children }) => <div style={{ fontWeight: 600, fontSize: 13, margin: "5px 0 2px" }}>{children}</div>,
  p:  ({ children }) => <div style={{ margin: "3px 0" }}>{children}</div>,
  ul: ({ children }) => <ul style={{ paddingLeft: 18, margin: "4px 0" }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ paddingLeft: 18, margin: "4px 0" }}>{children}</ol>,
  li: ({ children }) => <li style={{ margin: "2px 0" }}>{children}</li>,
  hr: () => <hr style={{ border: "none", borderTop: "1px solid rgba(0,0,0,0.1)", margin: "8px 0" }} />,
  strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
  table: ({ children }) => (
    <div style={{ overflowX: "auto", margin: "8px 0" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead style={{ background: "rgba(0,0,0,0.06)" }}>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr:   ({ children }) => <tr style={{ borderBottom: "1px solid rgba(0,0,0,0.08)" }}>{children}</tr>,
  th:   ({ children }) => <th style={{ padding: "6px 10px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>{children}</th>,
  td:   ({ children }) => <td style={{ padding: "5px 10px" }}>{children}</td>,
};

function Message({ msg }) {
  const isUser = msg.role === "user";
  const isError = msg.role === "assistant" && msg.content.startsWith("❌");

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 12,
        alignItems: "flex-start",
      }}
    >
      {!isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "#3b82f6",
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            marginRight: 8,
            flexShrink: 0,
            marginTop: 2,
          }}
        >
          🤖
        </div>
      )}

      <div
        style={{
          maxWidth: "72%",
          padding: "10px 14px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "#3b82f6" : isError ? "#fef2f2" : "#f3f4f6",
          color: isUser ? "#fff" : isError ? "#dc2626" : "#111827",
          fontSize: 14,
          lineHeight: 1.55,
          wordBreak: "break-word",
          overflowWrap: "break-word",
          border: isError ? "1px solid #fca5a5" : "none",
          minWidth: 0,
        }}
      >
        {isUser ? (
          <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
        ) : (
          <Markdown remarkPlugins={[remarkGfm]} components={mdComponents}>{msg.content}</Markdown>
        )}

        <div
          style={{
            fontSize: 10,
            opacity: 0.55,
            marginTop: 5,
            textAlign: isUser ? "right" : "left",
          }}
        >
          {new Date(msg.created_at).toLocaleTimeString()}
        </div>
      </div>

      {isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "#6b7280",
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            marginLeft: 8,
            flexShrink: 0,
            marginTop: 2,
          }}
        >
          👤
        </div>
      )}
    </div>
  );
}

const STEP_LABELS = {
  planning:    "Orchestrator планує...",
  evaluating:  "Оцінюю результат...",
  synthesizing: "Формую відповідь...",
};

function stepLabel(step) {
  if (!step) return "";
  if (step.event === "decision") {
    const agents = (step.agents || []).join(", ");
    return agents ? `Агенти: ${agents}` : "Рішення прийнято";
  }
  if (step.event === "agent_start")    return `Запускаю ${step.agent}...`;
  if (step.event === "agent_complete") return `${step.agent} ✓`;
  return STEP_LABELS[step.event] || step.event;
}

function StreamingMessage({ step, content }) {
  const hasContent = content && content.length > 0;

  return (
    <>
      <style>{`
        @keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0; } }
        .streaming-cursor { display: inline-block; width: 7px; height: 14px; background: #374151; border-radius: 1px; margin-left: 2px; vertical-align: text-bottom; animation: blink 1s step-end infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .step-spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid #d1d5db; border-top-color: #3b82f6; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 7px; vertical-align: middle; }
      `}</style>
      <div style={{ display: "flex", marginBottom: 12, alignItems: "flex-start" }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "#3b82f6",
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 14,
            marginRight: 8,
            flexShrink: 0,
            marginTop: 2,
          }}
        >
          🤖
        </div>

        <div
          style={{
            maxWidth: "72%",
            padding: "10px 14px",
            borderRadius: "18px 18px 18px 4px",
            background: "#f3f4f6",
            color: "#111827",
            fontSize: 14,
            lineHeight: 1.55,
            wordBreak: "break-word",
            overflowWrap: "break-word",
            minWidth: 0,
          }}
        >
          {hasContent ? (
            <>
              <Markdown remarkPlugins={[remarkGfm]} components={mdComponents}>{content}</Markdown>
              <span className="streaming-cursor" />
            </>
          ) : (
            <div style={{ color: "#6b7280", display: "flex", alignItems: "center" }}>
              <span className="step-spinner" />
              {stepLabel(step) || "Агенти працюють..."}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function MessageList({ messages, isProcessing, streamingStep, streamingContent }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
      {messages.length === 0 && !isProcessing && (
        <div
          style={{
            textAlign: "center",
            color: "#9ca3af",
            marginTop: 40,
            fontSize: 14,
          }}
        >
          <div style={{ fontSize: 40, marginBottom: 12 }}>🤖</div>
          <div>Напишіть завдання для команди агентів</div>
          <div style={{ fontSize: 12, marginTop: 8, color: "#d1d5db" }}>
            Наприклад: "Зроби аналітику по техпідтримці"
          </div>
        </div>
      )}

      {messages.map((msg) => (
        <Message key={msg.id} msg={msg} />
      ))}

      {isProcessing && (
        <StreamingMessage step={streamingStep} content={streamingContent || ""} />
      )}

      <div ref={bottomRef} />
    </div>
  );
}
