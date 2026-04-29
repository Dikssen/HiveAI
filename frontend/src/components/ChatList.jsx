import { useState } from "react";

function ChatItem({ chat, isActive, onSelect, onDelete }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onClick={() => onSelect(chat.id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: "10px 16px",
        cursor: "pointer",
        background: isActive ? "#334155" : "transparent",
        borderLeft: isActive ? "3px solid #3b82f6" : "3px solid transparent",
        transition: "background 0.15s",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: isActive ? 600 : 400,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          💬 {chat.title}
        </div>
        <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
          {new Date(chat.created_at).toLocaleDateString()}
        </div>
      </div>

      {hovered && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(chat.id);
          }}
          title="Delete chat"
          style={{
            background: "transparent",
            border: "none",
            color: "#64748b",
            cursor: "pointer",
            fontSize: 15,
            padding: "2px 4px",
            borderRadius: 4,
            flexShrink: 0,
            lineHeight: 1,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#64748b")}
        >
          ✕
        </button>
      )}
    </div>
  );
}

export default function ChatList({ chats, activeChatId, onSelect, onCreate, onDelete }) {
  return (
    <div
      style={{
        width: 260,
        minWidth: 260,
        background: "#1e293b",
        color: "#e2e8f0",
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "16px",
          borderBottom: "1px solid #334155",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>🐝 HiveAI</div>
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
            Multi-Agent Platform
          </div>
        </div>
        <button
          onClick={onCreate}
          title="New chat"
          style={{
            background: "#3b82f6",
            border: "none",
            borderRadius: 6,
            color: "#fff",
            cursor: "pointer",
            fontSize: 18,
            width: 32,
            height: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          +
        </button>
      </div>

      {/* Chat list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {chats.length === 0 && (
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              color: "#64748b",
              fontSize: 13,
            }}
          >
            Немає чатів.
            <br />
            Натисніть + щоб створити.
          </div>
        )}
        {chats.map((chat) => (
          <ChatItem
            key={chat.id}
            chat={chat}
            isActive={activeChatId === chat.id}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        ))}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid #334155",
          fontSize: 11,
          color: "#475569",
        }}
      >
        CrewAI + Ollama + Celery
      </div>
    </div>
  );
}
