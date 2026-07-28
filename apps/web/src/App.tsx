import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Archive,
  BookOpen,
  Braces,
  CalendarRange,
  ChevronRight,
  Database,
  Loader2,
  MessageSquareText,
  Search,
  Table2,
} from "lucide-react";
import {
  AgentStreamEvent,
  CompareRow,
  TimelineEvent,
  compareRegions,
  getEventDetail,
  streamAgentQuery,
} from "./api";

const defaultRegions = ["东亚", "中东", "中亚", "西欧"];

export function App() {
  const [question, setQuestion] = useState(
    "755年中国发生安史之乱时，中东和中亚发生了什么？",
  );
  const [startYear, setStartYear] = useState(700);
  const [endYear, setEndYear] = useState(800);
  const [regionsText, setRegionsText] = useState(defaultRegions.join("、"));
  const [rows, setRows] = useState<CompareRow[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null);
  const [agentEvents, setAgentEvents] = useState<AgentStreamEvent[]>([]);
  const [answer, setAnswer] = useState("");
  const [runId, setRunId] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [isComparing, setIsComparing] = useState(false);
  const [error, setError] = useState("");

  const regions = useMemo(
    () =>
      regionsText
        .split(/[、,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    [regionsText],
  );

  useEffect(() => {
    void handleCompare();
  }, []);

  async function handleAsk() {
    setIsAsking(true);
    setError("");
    setAnswer("");
    setRunId("");
    setAgentEvents([]);
    try {
      await streamAgentQuery(question, (event) => {
        setAgentEvents((current) => [...current, event]);
        if (event.run_id) setRunId(event.run_id);
        if (event.event === "final_answer") setAnswer(event.answer || "");
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent 请求失败");
    } finally {
      setIsAsking(false);
    }
  }

  async function handleCompare() {
    setIsComparing(true);
    setError("");
    try {
      const result = await compareRegions({ startYear, endYear, regions });
      setRows(result.rows);
      const firstEvent = result.rows.flatMap((row) => row.events)[0];
      if (firstEvent) {
        void handleSelectEvent(firstEvent.id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "横向对照请求失败");
    } finally {
      setIsComparing(false);
    }
  }

  async function handleSelectEvent(eventId: string) {
    try {
      const detail = await getEventDetail(eventId);
      if (detail.found) setSelectedEvent(detail.event);
    } catch (err) {
      setError(err instanceof Error ? err.message : "事件详情请求失败");
    }
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">Historical Timeline Agent</p>
          <h1>历史时间对照工作台</h1>
        </div>
        <div className="status-strip">
          <StatusPill icon={<Database size={15} />} label="PostgreSQL" value="online" />
          <StatusPill icon={<Activity size={15} />} label="SSE" value="stream" />
          <StatusPill icon={<Archive size={15} />} label="Redis" value="worker" />
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      <section className="workspace-grid">
        <aside className="query-panel">
          <PanelTitle icon={<Search size={18} />} title="查询控制" />
          <label className="field-label" htmlFor="question">
            Agent 问题
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={5}
          />
          <button className="primary-button" onClick={handleAsk} disabled={isAsking}>
            {isAsking ? <Loader2 className="spin" size={17} /> : <MessageSquareText size={17} />}
            运行 Agent
          </button>

          <div className="rule" />

          <PanelTitle icon={<CalendarRange size={18} />} title="横向对照" compact />
          <div className="year-grid">
            <label>
              开始年
              <input
                type="number"
                value={startYear}
                onChange={(event) => setStartYear(Number(event.target.value))}
              />
            </label>
            <label>
              结束年
              <input
                type="number"
                value={endYear}
                onChange={(event) => setEndYear(Number(event.target.value))}
              />
            </label>
          </div>
          <label className="field-label" htmlFor="regions">
            地区
          </label>
          <input
            id="regions"
            value={regionsText}
            onChange={(event) => setRegionsText(event.target.value)}
          />
          <button className="secondary-button" onClick={handleCompare} disabled={isComparing}>
            {isComparing ? <Loader2 className="spin" size={17} /> : <Table2 size={17} />}
            生成对照表
          </button>
        </aside>

        <section className="timeline-panel">
          <PanelTitle icon={<Table2 size={18} />} title={`${startYear}-${endYear} 年横向对照`} />
          <div className="timeline-table">
            {rows.map((row) => (
              <article className="region-row" key={row.region}>
                <div className="region-cell">{row.region}</div>
                <div className="event-lane">
                  {row.events.length ? (
                    row.events.map((event) => (
                      <button
                        className={`event-ticket ${
                          selectedEvent?.id === event.id ? "selected" : ""
                        }`}
                        key={event.id}
                        onClick={() => handleSelectEvent(event.id)}
                      >
                        <span className="event-year">{event.start_year}</span>
                        <strong>{event.title}</strong>
                        <small>{event.polity}</small>
                      </button>
                    ))
                  ) : (
                    <span className="empty-lane">暂无样例事件</span>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="detail-panel">
          <PanelTitle icon={<BookOpen size={18} />} title="事件详情与来源" />
          {selectedEvent ? (
            <EventDetail event={selectedEvent} />
          ) : (
            <div className="placeholder">选择对照表中的事件查看来源和影响。</div>
          )}
        </aside>
      </section>

      <section className="agent-grid">
        <div className="agent-steps">
          <PanelTitle icon={<Braces size={18} />} title="Agent 执行过程" />
          <div className="step-list">
            {agentEvents.map((event, index) => (
              <div className="step-line" key={`${event.event}-${index}`}>
                <span>{event.event}</span>
                <strong>{event.tool_name || event.status || event.run_id || "message"}</strong>
              </div>
            ))}
            {!agentEvents.length && <div className="placeholder">运行 Agent 后显示工具调用轨迹。</div>}
          </div>
        </div>
        <div className="agent-answer">
          <PanelTitle icon={<MessageSquareText size={18} />} title="Agent 分析" />
          {runId && <p className="run-id">run_id: {runId}</p>}
          <pre>{answer || "等待分析结果..."}</pre>
        </div>
      </section>
    </main>
  );
}

function StatusPill({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="status-pill">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function PanelTitle({
  icon,
  title,
  compact = false,
}: {
  icon: React.ReactNode;
  title: string;
  compact?: boolean;
}) {
  return (
    <div className={`panel-title ${compact ? "compact" : ""}`}>
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function EventDetail({ event }: { event: TimelineEvent }) {
  return (
    <div className="event-detail">
      <p className="eyebrow">{event.region} / {event.polity}</p>
      <h3>{event.title}</h3>
      <p>{event.summary}</p>
      <div className="metric-row">
        <span>{event.start_year}-{event.end_year || event.start_year}</span>
        <span>{event.source_status || "draft"}</span>
        <span>置信度 {Number(event.confidence || 0).toFixed(2)}</span>
      </div>
      <DetailList title="原因" items={event.causes || []} />
      <DetailList title="影响" items={event.effects || []} />
      <div className="source-list">
        <h4>来源</h4>
        {(event.sources || []).map((source) => (
          <article className="source-item" key={source.id}>
            <div>
              <strong>{source.source_title}</strong>
              <small>{source.source_type} / reliability {Number(source.reliability).toFixed(2)}</small>
            </div>
            <p>{source.citation || source.excerpt || "暂无引用文本"}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

function DetailList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="detail-list">
      <h4>{title}</h4>
      {items.map((item) => (
        <p key={item}>
          <ChevronRight size={14} />
          {item}
        </p>
      ))}
    </div>
  );
}
