const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Chats
  listChats: () => request("/chats"),
  createChat: (title = "New Chat") =>
    request("/chats", { method: "POST", body: JSON.stringify({ title }) }),
  getChat: (chatId) => request(`/chats/${chatId}`),
  getMessages: (chatId) => request(`/chats/${chatId}/messages`),

  deleteChat: (chatId) =>
    request(`/chats/${chatId}`, { method: "DELETE" }).catch(() => {}),

  // Send message — returns { message_id, task_id, status }
  sendMessage: (chatId, content) =>
    request(`/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  // Send message with SSE streaming — async generator that yields parsed events
  sendMessageStream: async function* (chatId, content) {
    const res = await fetch(`${BASE}/chats/${chatId}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try { yield JSON.parse(line.slice(6)); } catch {}
        }
      }
    }
  },

  // Tasks
  getTask: (taskId) => request(`/tasks/${taskId}`),

  // Agent runs
  getAgentRuns: (chatId) => request(`/chats/${chatId}/agent-runs`),
  getAgentRunLogs: (agentRunId) => request(`/agent-runs/${agentRunId}/logs`),

  // Health
  health: () => request("/health"),
  llmHealth: () => request("/health/llm"),
};
