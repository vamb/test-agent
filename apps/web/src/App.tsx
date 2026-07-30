import { useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  Link,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  ArrowLeft,
  ArrowUp,
  Bot,
  CalendarRange,
  ChevronRight,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Globe2,
  Loader2,
  MessageSquareText,
  PanelLeft,
  Search,
  Sparkles,
} from "lucide-react";
import {
  AdminEventDetailPage,
  AdminEventsPage,
  AdminImportCreatePage,
  AdminImportDetailPage,
  AdminImportsPage,
  AdminKnowledgeDetailPage,
  AdminKnowledgePage,
  AdminLayout,
  AdminOverviewPage,
  AdminQualityPage,
  AdminRelationsPage,
  AdminVectorsPage,
} from "./AdminPages";
import {
  AgentStreamEvent,
  AgentLink,
  AgentReference,
  CompareRow,
  TimelineEvent,
  compareRegions,
  getEventDetail,
  streamAgentQuery,
} from "./api";

const defaultQuestion = "755年中国发生安史之乱时，中东、中亚和西欧发生了什么？";
const defaultRegions = ["东亚", "中东", "中亚", "西欧"];

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "done" | "error";
  runId?: string;
  steps?: AgentStreamEvent[];
  events?: TimelineEvent[];
  references?: AgentReference[];
  links?: AgentLink[];
};

export function App() {
  return (
    <BrowserRouter>
      <main className="app-frame">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/events/:eventId" element={<EventDetailPage />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminOverviewPage />} />
            <Route path="imports" element={<AdminImportsPage />} />
            <Route path="imports/new" element={<AdminImportCreatePage />} />
            <Route path="imports/:batchId" element={<AdminImportDetailPage />} />
            <Route path="events" element={<AdminEventsPage />} />
            <Route path="events/:eventId" element={<AdminEventDetailPage />} />
            <Route path="relations" element={<AdminRelationsPage />} />
            <Route path="quality" element={<AdminQualityPage />} />
            <Route path="knowledge" element={<AdminKnowledgePage />} />
            <Route path="knowledge/:documentId" element={<AdminKnowledgeDetailPage />} />
            <Route path="vectors" element={<AdminVectorsPage />} />
          </Route>
        </Routes>
      </main>
    </BrowserRouter>
  );
}

function ChatPage() {
  const [question, setQuestion] = useState(defaultQuestion);
  const [startYear, setStartYear] = useState(700);
  const [endYear, setEndYear] = useState(800);
  const [regionsText, setRegionsText] = useState(defaultRegions.join("、"));
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      status: "done",
      content:
        "你可以问一个历史时间点，我会尽量把同一时期不同地区发生的事情放在一起比较。回答里的事件卡片可以点击进入详情页。",
    },
  ]);
  const [isAsking, setIsAsking] = useState(false);
  const [isComparing, setIsComparing] = useState(false);

  const regions = useMemo(
    () =>
      regionsText
        .split(/[、,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    [regionsText],
  );

  async function handleAsk() {
    const input = question.trim();
    if (!input || isAsking) return;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: input,
    };
    const assistantId = crypto.randomUUID();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "正在分析时间线与地区关联...",
      status: "streaming",
      steps: [],
      events: [],
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setIsAsking(true);

    try {
      await streamAgentQuery(input, (event) => {
        setMessages((current) =>
          current.map((message) => {
            if (message.id !== assistantId) return message;
            const steps = [...(message.steps || []), event];
            const events = mergeEvents(message.events || [], event.events || []);
            const references = mergeReferences(message.references || [], event.references || []);
            const links = mergeLinks(message.links || [], event.links || []);
            return {
              ...message,
              runId: event.run_id || message.runId,
              steps,
              events,
              references,
              links,
              content:
                event.event === "final_answer"
                  ? event.answer || message.content
                  : message.content,
              status: event.event === "final_answer" ? "done" : "streaming",
            };
          }),
        );
      });
    } catch (err) {
      const errorText = err instanceof Error ? err.message : "Agent 请求失败";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: errorText, status: "error" }
            : message,
        ),
      );
    } finally {
      setIsAsking(false);
    }
  }

  async function handleCompare() {
    if (isComparing || !regions.length) return;
    setIsComparing(true);
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: `对照 ${startYear}-${endYear} 年：${regions.join("、")}`,
      },
      {
        id: assistantId,
        role: "assistant",
        content: "正在生成横向历史对照...",
        status: "streaming",
        events: [],
        steps: [],
      },
    ]);

    try {
      const result = await compareRegions({ startYear, endYear, regions });
      const events = result.rows.flatMap((row) => row.events);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                status: "done",
                content: buildCompareSummary(result.rows, startYear, endYear),
                events,
              }
            : message,
        ),
      );
    } catch (err) {
      const errorText = err instanceof Error ? err.message : "横向对照请求失败";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, content: errorText, status: "error" }
            : message,
        ),
      );
    } finally {
      setIsComparing(false);
    }
  }

  return (
    <div className="chat-layout">
      <aside className="conversation-rail">
        <div className="brand-mark">
          <div className="brand-symbol">
            <Globe2 size={22} />
          </div>
          <div>
            <strong>历史时间对照 Agent</strong>
            <span>AI research workspace</span>
          </div>
        </div>

        <button className="rail-action" onClick={() => setQuestion(defaultQuestion)}>
          <MessageSquareText size={17} />
          新建提问
        </button>

        <Link className="rail-action subtle" to="/admin">
          <Database size={17} />
          数据管理台
        </Link>

        <div className="rail-section">
          <p>快捷对照</p>
          <div className="year-inputs">
            <label>
              开始
              <input
                type="number"
                value={startYear}
                onChange={(event) => setStartYear(Number(event.target.value))}
              />
            </label>
            <label>
              结束
              <input
                type="number"
                value={endYear}
                onChange={(event) => setEndYear(Number(event.target.value))}
              />
            </label>
          </div>
          <label className="rail-label">
            地区
            <input
              value={regionsText}
              onChange={(event) => setRegionsText(event.target.value)}
            />
          </label>
          <button className="rail-action subtle" onClick={handleCompare} disabled={isComparing}>
            {isComparing ? <Loader2 className="spin" size={17} /> : <CalendarRange size={17} />}
            生成横向对照
          </button>
        </div>

        <div className="rail-section quiet">
          <p>当前服务</p>
          <span>Frontend 5174</span>
          <span>Backend 19000</span>
          <span>PostgreSQL connected</span>
        </div>
      </aside>

      <section className="chat-surface">
        <header className="chat-header">
          <button className="icon-button" aria-label="toggle sidebar">
            <PanelLeft size={19} />
          </button>
          <div>
            <p className="eyebrow">Timeline conversation</p>
            <h1>从聊天进入历史档案</h1>
          </div>
          <div className="header-status">
            <Sparkles size={16} />
            <span>Function calling + SSE</span>
          </div>
        </header>

        <div className="message-list">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>

        <section className="composer">
          <div className="composer-inner">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleAsk();
                }
              }}
              rows={2}
              placeholder="输入一个历史时间点或问题，例如：公元750年前后各地区发生了什么？"
            />
            <button className="send-button" onClick={handleAsk} disabled={isAsking}>
              {isAsking ? <Loader2 className="spin" size={19} /> : <ArrowUp size={19} />}
            </button>
          </div>
        </section>
      </section>
    </div>
  );
}

function MessageBubble({
  message,
}: {
  message: ChatMessage;
}) {
  const steps = message.steps || [];
  const events = message.events || [];
  const references = message.references || [];
  const externalLinks = (message.links || []).filter((link) => link.external);

  return (
    <article className={`message-row ${message.role}`}>
      <div className="message-avatar">
        {message.role === "assistant" ? <Bot size={18} /> : <span>你</span>}
      </div>
      <div className="message-body">
        <div className={`message-card ${message.status === "error" ? "error" : ""}`}>
          {message.status === "streaming" && (
            <div className="streaming-line">
              <Loader2 className="spin" size={15} />
              <span>正在读取工具返回...</span>
            </div>
          )}
          <p>{message.content}</p>
          {message.runId && <small className="run-id">run_id: {message.runId}</small>}
        </div>

        {events.length > 0 && (
          <div className="result-cluster">
            <div className="cluster-title">
              <Search size={15} />
              <span>可查看的事件详情</span>
            </div>
            <div className="event-card-grid">
              {events.slice(0, 8).map((event) => (
                <Link
                  className="event-link-card"
                  key={event.id}
                  to={`/events/${encodeURIComponent(event.id)}`}
                >
                  <div>
                    <span>{event.start_year}</span>
                    <strong>{event.title}</strong>
                    <small>{event.region} / {event.polity}</small>
                  </div>
                  <ExternalLink size={16} />
                </Link>
              ))}
            </div>
          </div>
        )}

        {references.length > 0 && (
          <div className="result-cluster compact">
            <div className="cluster-title">
              <FileText size={15} />
              <span>引用来源</span>
            </div>
            <div className="reference-list">
              {references.slice(0, 5).map((reference) => (
                <div className="reference-item" key={`${reference.id}-${reference.title}`}>
                  <strong>{reference.title}</strong>
                  <small>{reference.citation || reference.event_title}</small>
                </div>
              ))}
            </div>
          </div>
        )}

        {externalLinks.length > 0 && (
          <div className="result-cluster compact">
            <div className="cluster-title">
              <ExternalLink size={15} />
              <span>外部追踪</span>
            </div>
            <div className="external-link-list">
              {externalLinks.map((link) => (
                <a
                  className="external-trace-link"
                  key={`${link.type}-${link.href}`}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>{link.title}</span>
                  <ExternalLink size={14} />
                </a>
              ))}
            </div>
          </div>
        )}

        {steps.length > 0 && (
          <details className="tool-trace">
            <summary>查看 Agent 执行过程</summary>
            {steps.map((step, index) => (
              <div className="trace-line" key={`${step.event}-${index}`}>
                <span>{step.event}</span>
                <strong>{step.tool_name || step.status || step.run_id || "message"}</strong>
              </div>
            ))}
          </details>
        )}
      </div>
    </article>
  );
}

function EventDetailPage() {
  const navigate = useNavigate();
  const { eventId = "" } = useParams();
  const [event, setEvent] = useState<TimelineEvent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    void getEventDetail(eventId)
      .then((detail) => {
        if (!detail.found) {
          setError("没有找到这个事件。");
          setEvent(null);
          return;
        }
        setEvent(detail.event);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "事件详情请求失败"))
      .finally(() => setLoading(false));
  }, [eventId]);

  return (
    <section className="detail-page">
      <header className="detail-topbar">
        <button className="back-button" onClick={() => navigate("/")}>
          <ArrowLeft size={18} />
          返回聊天
        </button>
        <p className="eyebrow">Historical archive</p>
      </header>

      {loading && (
        <div className="detail-loading">
          <Loader2 className="spin" size={22} />
          正在读取事件档案...
        </div>
      )}

      {!loading && error && <div className="error-banner">{error}</div>}

      {!loading && event && (
        <article className="archive-document">
          <div className="archive-kicker">
            <span>{event.region}</span>
            <span>{event.polity}</span>
            <span>{event.source_status || "draft"}</span>
          </div>
          <h1>{event.title}</h1>
          <div className="archive-meta">
            <span>
              <Clock3 size={15} />
              {event.start_year}-{event.end_year || event.start_year}
            </span>
            <span>置信度 {Number(event.confidence || 0).toFixed(2)}</span>
          </div>

          <section className="archive-section lead">
            <h2>事件摘要</h2>
            <p>{event.summary}</p>
          </section>

          <div className="archive-columns">
            <ArchiveList title="前因" items={event.causes || []} />
            <ArchiveList title="影响" items={event.effects || []} />
          </div>

          <section className="archive-section">
            <h2>来源与引用</h2>
            {(event.sources || []).length ? (
              <div className="source-grid">
                {(event.sources || []).map((source) => (
                  <article className="source-record" key={source.id}>
                    <FileText size={18} />
                    <div>
                      <strong>{source.source_title}</strong>
                      <span>
                        {source.source_type} / reliability{" "}
                        {Number(source.reliability || 0).toFixed(2)}
                      </span>
                      <p>{source.citation || source.excerpt || "暂无引用文本"}</p>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted-text">这个事件还没有绑定来源。</p>
            )}
          </section>
        </article>
      )}
    </section>
  );
}

function ArchiveList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="archive-section">
      <h2>{title}</h2>
      {items.length ? (
        items.map((item) => (
          <p className="archive-list-item" key={item}>
            <ChevronRight size={15} />
            {item}
          </p>
        ))
      ) : (
        <p className="muted-text">暂无结构化记录。</p>
      )}
    </section>
  );
}

function mergeEvents(current: TimelineEvent[], next: TimelineEvent[]) {
  const byId = new Map<string, TimelineEvent>();
  [...current, ...next].forEach((event) => byId.set(event.id, event));
  return [...byId.values()];
}

function mergeReferences(current: AgentReference[], next: AgentReference[]) {
  const byId = new Map<string, AgentReference>();
  [...current, ...next].forEach((reference) => {
    const key = reference.id || `${reference.event_id}-${reference.title}-${reference.citation}`;
    byId.set(key, reference);
  });
  return [...byId.values()];
}

function mergeLinks(current: AgentLink[], next: AgentLink[]) {
  const byHref = new Map<string, AgentLink>();
  [...current, ...next].forEach((link) => {
    const key = `${link.type}-${link.href}`;
    byHref.set(key, link);
  });
  return [...byHref.values()];
}

function buildCompareSummary(rows: CompareRow[], startYear: number, endYear: number) {
  const total = rows.reduce((sum, row) => sum + row.events.length, 0);
  const activeRegions = rows.filter((row) => row.events.length).map((row) => row.region);
  if (!total) {
    return `${startYear}-${endYear} 年暂时没有检索到这些地区的样例事件。`;
  }
  return `${startYear}-${endYear} 年共检索到 ${total} 条事件，涉及 ${activeRegions.join("、")}。你可以点击下方事件卡片查看详细档案。`;
}
