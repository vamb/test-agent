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
  observation?: Record<string, unknown>;
  tool_arguments?: Record<string, unknown>;
  error_message?: string;
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
) {
  const response = await fetch(`${API_BASE_URL}/agent/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
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
      const dataLine = frame
        .split("\n")
        .find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      onEvent(JSON.parse(dataLine.slice(6)) as AgentStreamEvent);
    }
  }
}
