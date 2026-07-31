export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:19000";

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
  const response = await fetch(`${API_BASE_URL}/compare/regions?${search}`);
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
  const response = await fetch(`${API_BASE_URL}/events/${eventId}`);
  if (!response.ok) {
    throw new Error(`事件详情请求失败：${response.status}`);
  }
  return (await response.json()) as { found: boolean; event: TimelineEvent };
}

export async function streamAgentQuery(
  input: string,
  onEvent: (event: AgentStreamEvent) => void,
  options?: { signal?: AbortSignal },
) {
  const response = await fetch(`${API_BASE_URL}/agent/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
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
  const response = await fetch(`${API_BASE_URL}/agent/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const response = await fetch(`${API_BASE_URL}/agent/runs/${encodeURIComponent(runId)}/confirm`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Agent 确认恢复失败：${response.status}`);
  }
  return (await response.json()) as AgentConfirmResponse;
}
