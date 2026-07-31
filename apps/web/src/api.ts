const browserApiHost =
  typeof window === "undefined" ? "127.0.0.1" : window.location.hostname || "127.0.0.1";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || `http://${browserApiHost}:19000`;

export type TimelineEvent = {
  id: string;
  title: string;
  start_year: number;
  end_year?: number;
  region: string;
  polity: string;
  summary: string;
  source_status?: string;
  confidence?: number;
  sources?: EventSourceRecord[];
  causes?: string[];
  effects?: string[];
};

export type EventSourceRecord = {
  id: string;
  source_title: string;
  source_type: string;
  citation: string;
  excerpt: string;
  reliability: number;
  is_primary?: boolean;
};

export type CompareRow = {
  region: string;
  events: TimelineEvent[];
};

export type AgentStreamEvent = {
  event: string;
  run_id?: string;
  conversation_id?: string;
  input_message_id?: string;
  output_message_id?: string;
  step_index?: number;
  tool_name?: string;
  status?: string;
  answer?: string;
  delta?: string;
  events?: TimelineEvent[];
  references?: AgentReference[];
  links?: AgentLink[];
  observation?: Record<string, unknown>;
  tool_arguments?: Record<string, unknown>;
  error_message?: string;
};

export type AgentConfirmResponse = {
  confirmed: boolean;
  run_id?: string;
  answer?: string;
  events?: TimelineEvent[];
  references?: AgentReference[];
  links?: AgentLink[];
  steps?: AgentStreamEvent[];
};

export type AgentReference = {
  id: string;
  title: string;
  source_type: string;
  citation: string;
  excerpt: string;
  event_id: string;
  event_title: string;
  reliability?: number;
  document_id?: string;
  chunk_id?: string;
  score?: number;
};

export type AgentLink = {
  type: string;
  target_id?: string;
  title: string;
  href: string;
  external?: boolean;
};

export type AuthUser = {
  id: string;
  username: string;
  email?: string;
  display_name: string;
  role: string;
  status: string;
};

export type ChatGroup = {
  id: string;
  user_id: string;
  title: string;
  description: string;
  pinned: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
};

export type ChatConversation = {
  id: string;
  user_id: string;
  group_id?: string | null;
  title: string;
  summary: string;
  status: string;
  last_message_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type StoredChatMessage = {
  id: string;
  conversation_id: string;
  user_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  content_format: string;
  status: "streaming" | "done" | "error" | "cancelled";
  agent_run_id?: string | null;
  parent_message_id?: string | null;
  metadata_json?: Record<string, unknown>;
  artifacts?: {
    event?: TimelineEvent[];
    reference?: AgentReference[];
    link?: AgentLink[];
  };
  created_at: string;
};

async function apiFetch(path: string, options: RequestInit = {}) {
  return fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
}

export async function registerUser(params: {
  username: string;
  password: string;
  email?: string;
  displayName?: string;
}) {
  const response = await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username: params.username,
      password: params.password,
      email: params.email || "",
      display_name: params.displayName || "",
    }),
  });
  if (!response.ok) {
    throw new Error(`注册失败：${response.status}`);
  }
  return (await response.json()) as { user: AuthUser };
}

export async function loginUser(username: string, password: string) {
  const response = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(`登录失败：${response.status}`);
  }
  return (await response.json()) as { user: AuthUser };
}

export async function logoutUser() {
  const response = await apiFetch("/auth/logout", { method: "POST" });
  if (!response.ok) {
    throw new Error(`登出失败：${response.status}`);
  }
  return (await response.json()) as { logged_out: boolean; revoked: boolean };
}

export async function getCurrentUser() {
  const response = await apiFetch("/auth/me");
  if (response.status === 401) return null;
  if (!response.ok) {
    throw new Error(`读取当前用户失败：${response.status}`);
  }
  return ((await response.json()) as { user: AuthUser }).user;
}

export async function listChatConversations() {
  const response = await apiFetch("/chat/conversations");
  if (!response.ok) {
    throw new Error(`读取会话列表失败：${response.status}`);
  }
  return (await response.json()) as { conversations: ChatConversation[] };
}

export async function createChatConversation(title = "新会话") {
  const response = await apiFetch("/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`创建会话失败：${response.status}`);
  }
  return (await response.json()) as { conversation: ChatConversation };
}

export async function getChatConversation(conversationId: string) {
  const response = await apiFetch(`/chat/conversations/${encodeURIComponent(conversationId)}`);
  if (!response.ok) {
    throw new Error(`读取会话失败：${response.status}`);
  }
  return (await response.json()) as {
    conversation: ChatConversation;
    messages: StoredChatMessage[];
  };
}

export async function compareRegions(params: {
  startYear: number;
  endYear: number;
  regions: string[];
}) {
  const search = new URLSearchParams({
    start_year: String(params.startYear),
    end_year: String(params.endYear),
  });
  params.regions.forEach((region) => search.append("regions", region));
  const response = await apiFetch(`/compare/regions?${search}`);
  if (!response.ok) {
    throw new Error(`横向对照请求失败：${response.status}`);
  }
  return (await response.json()) as {
    start_year: number;
    end_year: number;
    rows: CompareRow[];
  };
}

export async function getEventDetail(eventId: string) {
  const response = await apiFetch(`/events/${eventId}`);
  if (!response.ok) {
    throw new Error(`事件详情请求失败：${response.status}`);
  }
  return (await response.json()) as { found: boolean; event: TimelineEvent };
}

export async function streamAgentQuery(
  input: string,
  onEvent: (event: AgentStreamEvent) => void,
  options?: { signal?: AbortSignal; conversationId?: string },
) {
  const response = await apiFetch("/agent/query/stream", {
    method: "POST",
    body: JSON.stringify({
      input,
      conversation_id: options?.conversationId || undefined,
    }),
    signal: options?.signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Agent SSE 请求失败：${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const dataLines = frame
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6));
      if (!dataLines.length) continue;
      try {
        onEvent(JSON.parse(dataLines.join("\n")) as AgentStreamEvent);
      } catch {
        onEvent({ event: "client_parse_error", error_message: dataLines.join("\n") });
      }
    }
  }
}

export async function cancelAgentRun(runId: string, reason = "Cancelled from web UI") {
  const response = await apiFetch(`/agent/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) {
    throw new Error(`Agent 取消失败：${response.status}`);
  }
  return (await response.json()) as {
    run_id: string;
    cancelled: boolean;
    status: string;
  };
}

export async function confirmAgentRun(runId: string) {
  const response = await apiFetch(`/agent/runs/${encodeURIComponent(runId)}/confirm`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Agent 确认恢复失败：${response.status}`);
  }
  return (await response.json()) as AgentConfirmResponse;
}
