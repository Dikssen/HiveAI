import { useState, useEffect } from "react";
import { api } from "./api/client";
import ChatList from "./components/ChatList";
import ChatWindow from "./components/ChatWindow";

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [llmStatus, setLlmStatus] = useState(null);

  const loadChats = async () => {
    try {
      const data = await api.listChats();
      setChats(data);
    } catch {
      // backend not ready yet
    }
  };

  useEffect(() => {
    loadChats();
    api.llmHealth().then(setLlmStatus).catch(() => {});
  }, []);

  const handleCreateChat = async () => {
    try {
      const chat = await api.createChat("New Chat");
      setChats((prev) => [chat, ...prev]);
      setActiveChatId(chat.id);
    } catch (e) {
      alert("Failed to create chat: " + e.message);
    }
  };

  const handleSelectChat = (id) => {
    setActiveChatId(id);
    loadChats();
  };

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        overflow: "hidden", // ← не дає сторінці рости за межі viewport
      }}
    >
      <ChatList
        chats={chats}
        activeChatId={activeChatId}
        onSelect={handleSelectChat}
        onCreate={handleCreateChat}
      />

      {/* Права панель — займає весь залишок висоти */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          minHeight: 0, // ← ключово для скролу в дочірньому flex-елементі
          overflow: "hidden",
        }}
      >
        {llmStatus && llmStatus.status !== "ok" && (
          <div
            style={{
              background: "#fff7ed",
              borderBottom: "1px solid #fed7aa",
              padding: "8px 16px",
              fontSize: 13,
              color: "#92400e",
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            ⚠️ <strong>LLM Warning:</strong> {llmStatus.message}
          </div>
        )}
        <ChatWindow chatId={activeChatId} />
      </div>
    </div>
  );
}
