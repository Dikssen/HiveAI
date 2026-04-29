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
  return res.json();
}

export const api = {
  // Chats
  listChats: () => request("/chats"),
  createChat: (title = "New Chat") =>
    request("/chats", { method: "POST", body: JSON.stringify({ title }) }),
  getChat: (chatId) => request(`/chats/${chatId}`),
  getMessages: (chatId) => request(`/chats/${chatId}/messages`),

  // Send message — returns { message_id, task_id, status }
  sendMessage: (chatId, content) =>
    request(`/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  // Tasks
  getTask: (taskId) => request(`/tasks/${taskId}`),

  // Agent runs
  getAgentRuns: (chatId) => request(`/chats/${chatId}/agent-runs`),
  getAgentRunLogs: (agentRunId) => request(`/agent-runs/${agentRunId}/logs`),

  // Health
  health: () => request("/health"),
  llmHealth: () => request("/health/llm"),
};
