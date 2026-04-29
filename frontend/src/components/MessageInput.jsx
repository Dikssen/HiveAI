import { useState } from "react";

export default function MessageInput({ onSend, disabled }) {
  const [text, setText] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      handleSubmit(e);
    }
  };

  const examples = [
    "Зроби аналітику по техпідтримці",
    "Подивись логи і знайди помилки",
    "Зроби ревʼю коду",
    "Перевір docker конфігурацію",
    "Підготуй план реалізації нової фічі",
  ];

  return (
    <div
      style={{
        borderTop: "1px solid #e5e7eb",
        padding: "12px 16px",
        background: "#fff",
      }}
    >
      {!disabled && text === "" && (
        <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
          {examples.map((ex) => (
            <button
              key={ex}
              onClick={() => setText(ex)}
              style={{
                padding: "4px 10px",
                fontSize: 11,
                background: "#eff6ff",
                border: "1px solid #bfdbfe",
                borderRadius: 9999,
                cursor: "pointer",
                color: "#3b82f6",
                whiteSpace: "nowrap",
              }}
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? "Агенти працюють..." : "Напишіть завдання... (Enter для відправки)"}
          rows={2}
          style={{
            flex: 1,
            padding: "10px 12px",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            fontSize: 14,
            resize: "none",
            fontFamily: "inherit",
            outline: "none",
            background: disabled ? "#f9fafb" : "#fff",
          }}
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          style={{
            padding: "0 20px",
            background: disabled || !text.trim() ? "#9ca3af" : "#3b82f6",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            cursor: disabled || !text.trim() ? "not-allowed" : "pointer",
            fontSize: 14,
            fontWeight: 600,
            alignSelf: "stretch",
          }}
        >
          →
        </button>
      </form>
    </div>
  );
}
