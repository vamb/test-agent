import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
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
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Globe2,
  History,
  Loader2,
  LogIn,
  LogOut,
  MessageSquareText,
  PanelLeft,
  Plus,
  Search,
  ShieldAlert,
  Sparkles,
  Square,
  UserRound,
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
  AuthUser,
  ChatConversation,
  AgentLink,
  AgentReference,
  CompareRow,
  StoredChatMessage,
  TimelineEvent,
  cancelAgentRun,
  createChatConversation,
  confirmAgentRun,
  compareRegions,
  getChatConversation,
  getCurrentUser,
  getEventDetail,
  listChatConversations,
  loginUser,
  logoutUser,
  registerUser,
  streamAgentQuery,
} from "./api";

const defaultQuestion = "755年中国发生安史之乱时，中东、中亚和西欧发生了什么？";
const defaultRegions = ["东亚", "中东", "中亚", "西欧"];

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "waiting_confirmation" | "confirming" | "done" | "error" | "cancelled";
  phase?: string;
  runId?: string;
  steps?: AgentStreamEvent[];
  events?: TimelineEvent[];
  references?: AgentReference[];
  links?: AgentLink[];
  confirmation?: {
    toolName: string;
    toolArguments: Record<string, unknown>;
    error?: string;
  };
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
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({ username: "", password: "" });
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string>("");
  const [conversationError, setConversationError] = useState("");
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [question, setQuestion] = useState(defaultQuestion);
  const [startYear, setStartYear] = useState(700);
  const [endYear, setEndYear] = useState(800);
  const [regionsText, setRegionsText] = useState(defaultRegions.join("、"));
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage()]);
  const [isAsking, setIsAsking] = useState(false);
  const [isComparing, setIsComparing] = useState(false);
  const [stickToBottom, setStickToBottom] = useState(true);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const activeControllerRef = useRef<AbortController | null>(null);
  const activeRunIdRef = useRef<string>("");
  const activeAssistantIdRef = useRef<string>("");
  const lastQuestionRef = useRef(defaultQuestion);

  const regions = useMemo(
    () =>
      regionsText
        .split(/[、,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    [regionsText],
  );

  useEffect(() => {
    void getCurrentUser()
      .then((user) => {
        setCurrentUser(user);
        if (user) void refreshConversations();
      })
      .catch((err) => setAuthError(err instanceof Error ? err.message : "读取用户失败"))
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (!stickToBottom) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stickToBottom]);

  useEffect(() => {
    const onScroll = () => {
      const distanceFromBottom =
        document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
      setStickToBottom(distanceFromBottom < 120);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function resizeComposer() {
    const textarea = composerRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }

  function scrollToLatest() {
    setStickToBottom(true);
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  async function refreshConversations() {
    setConversationsLoading(true);
    setConversationError("");
    try {
      const result = await listChatConversations();
      setConversations(result.conversations);
    } catch (err) {
      setConversationError(err instanceof Error ? err.message : "读取会话失败");
    } finally {
      setConversationsLoading(false);
    }
  }

  async function handleAuthSubmit() {
    const username = authForm.username.trim();
    const password = authForm.password;
    if (!username || !password || authLoading) return;
    setAuthLoading(true);
    setAuthError("");
    try {
      if (authMode === "register") {
        await registerUser({ username, password });
      }
      const result = await loginUser(username, password);
      setCurrentUser(result.user);
      setAuthForm({ username: "", password: "" });
      await refreshConversations();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "认证失败");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogout() {
    await logoutUser();
    setCurrentUser(null);
    setConversations([]);
    setActiveConversationId("");
    setMessages([welcomeMessage()]);
  }

  function handleNewConversation() {
    setActiveConversationId("");
    setMessages([welcomeMessage()]);
    setQuestion(defaultQuestion);
    setConversationError("");
  }

  async function handleCreateConversation() {
    if (!currentUser) return;
    setConversationError("");
    try {
      const result = await createChatConversation("新历史研究");
      setActiveConversationId(result.conversation.id);
      setConversations((current) => [result.conversation, ...current]);
      setMessages([welcomeMessage()]);
    } catch (err) {
      setConversationError(err instanceof Error ? err.message : "创建会话失败");
    }
  }

  async function handleLoadConversation(conversationId: string) {
    if (!currentUser || isAsking) return;
    setConversationError("");
    try {
      const result = await getChatConversation(conversationId);
      setActiveConversationId(result.conversation.id);
      setMessages(messagesFromStored(result.messages));
      setStickToBottom(true);
    } catch (err) {
      setConversationError(err instanceof Error ? err.message : "读取会话失败");
    }
  }

  async function handleAsk() {
    const input = question.trim();
    if (!input || isAsking) return;
    const controller = new AbortController();
    activeControllerRef.current = controller;
    activeRunIdRef.current = "";
    lastQuestionRef.current = input;

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: input,
    };
    const assistantId = crypto.randomUUID();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      status: "streaming",
      phase: "正在准备历史检索...",
      steps: [],
      events: [],
    };
    activeAssistantIdRef.current = assistantId;

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setQuestion("");
    requestAnimationFrame(resizeComposer);
    setStickToBottom(true);
    setIsAsking(true);

    try {
      await streamAgentQuery(input, (event) => {
        if (event.event === "chat_context" && event.conversation_id) {
          setActiveConversationId(event.conversation_id);
        }
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
              phase: describeStreamEvent(event),
              steps,
              events,
              references,
              links,
              content:
                event.event === "answer_delta"
                  ? `${message.content}${event.delta || ""}`
                  : event.event === "final_answer" || event.event === "confirmation_required"
                  ? event.answer || message.content
                  : event.event === "run_failed"
                    ? event.error_message || "Agent 请求失败"
                    : event.event === "run_cancelled"
                      ? event.error_message || "已停止生成。"
                  : message.content,
              status:
                event.event === "final_answer"
                  ? "done"
                  : event.event === "confirmation_required"
                    ? "waiting_confirmation"
                    : event.event === "run_failed"
                      ? "error"
                      : event.event === "run_cancelled"
                        ? "cancelled"
                        : "streaming",
              confirmation:
                event.event === "confirmation_required"
                  ? {
                      toolName: event.tool_name || "unknown_tool",
                      toolArguments: event.tool_arguments || {},
                    }
                  : message.confirmation,
            };
          }),
        );
        if (event.run_id) activeRunIdRef.current = event.run_id;
        if (event.event === "final_answer" || event.event === "confirmation_required") {
          void refreshConversations();
        }
      }, { signal: controller.signal, conversationId: activeConversationId || undefined });
    } catch (err) {
      if (controller.signal.aborted) {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: message.content || "已停止生成。",
                  status: "cancelled",
                  phase: "已停止",
                }
              : message,
          ),
        );
        return;
      }
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
      activeControllerRef.current = null;
      activeAssistantIdRef.current = "";
    }
  }

  async function handleStop() {
    const runId = activeRunIdRef.current;
    activeControllerRef.current?.abort();
    if (runId) {
      try {
        await cancelAgentRun(runId);
      } catch {
        // Local abort already stopped the UI; backend cancellation is best effort.
      }
    }
    const assistantId = activeAssistantIdRef.current;
    if (assistantId) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: message.content || "已停止生成。",
                status: "cancelled",
                phase: "已停止",
              }
            : message,
        ),
      );
    }
    setIsAsking(false);
  }

  async function handleConfirmRun(messageId: string) {
    const target = messages.find((message) => message.id === messageId);
    if (!target?.runId || target.status === "confirming") return;

    setMessages((current) =>
      current.map((message) =>
        message.id === messageId
          ? {
              ...message,
              status: "confirming",
              confirmation: message.confirmation
                ? { ...message.confirmation, error: undefined }
                : message.confirmation,
            }
          : message,
      ),
    );

    try {
      const result = await confirmAgentRun(target.runId);
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== messageId) return message;
          const confirmedSteps = (result.steps || []).map((step) => ({
            ...step,
            event: step.event || "confirmed_tool_result",
            run_id: step.run_id || result.run_id || message.runId,
          }));
          return {
            ...message,
            status: "done",
            runId: result.run_id || message.runId,
            content: result.answer || message.content,
            events: mergeEvents(message.events || [], result.events || []),
            references: mergeReferences(message.references || [], result.references || []),
            links: mergeLinks(message.links || [], result.links || []),
            steps: [...(message.steps || []), ...confirmedSteps],
            confirmation: undefined,
          };
        }),
      );
    } catch (err) {
      const errorText = err instanceof Error ? err.message : "确认恢复失败";
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId
            ? {
                ...message,
                status: "waiting_confirmation",
                confirmation: message.confirmation
                  ? { ...message.confirmation, error: errorText }
                  : {
                      toolName: "unknown_tool",
                      toolArguments: {},
                      error: errorText,
                    },
              }
            : message,
        ),
      );
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

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId,
  );
  const headerTitle = activeConversation?.title || "新的历史研究";

  if (!authChecked) {
    return (
      <div className="auth-screen">
        <div className="auth-loading">
          <Loader2 className="spin" size={20} />
          正在检查登录状态...
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <AuthScreen
        authMode={authMode}
        authForm={authForm}
        authError={authError}
        authLoading={authLoading}
        onModeChange={(mode) => {
          setAuthMode(mode);
          setAuthError("");
        }}
        onFormChange={setAuthForm}
        onSubmit={() => void handleAuthSubmit()}
      />
    );
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
            <span>Timeline research workspace</span>
          </div>
        </div>

        <div className="user-card compact">
          <UserRound size={17} />
          <div>
            <strong>{currentUser.display_name || currentUser.username}</strong>
            <span>{currentUser.role} / 已登录</span>
          </div>
          <button className="mini-icon-button" onClick={() => void handleLogout()} aria-label="登出">
            <LogOut size={15} />
          </button>
        </div>

        <button className="rail-action primary" onClick={() => void handleCreateConversation()}>
          <Plus size={17} />
          新建会话
        </button>

        <div className="rail-section conversation-section">
          <div className="rail-section-head">
            <p>聊天记录</p>
            <button className="mini-icon-button" onClick={handleNewConversation} aria-label="临时提问">
              <MessageSquareText size={15} />
            </button>
          </div>
          {conversationError && <small className="rail-error">{conversationError}</small>}
          {conversationsLoading ? (
            <div className="rail-loading">
              <Loader2 className="spin" size={15} />
              读取会话...
            </div>
          ) : (
            <div className="conversation-list">
              {conversations.length === 0 && <span className="empty-hint">还没有保存的聊天。</span>}
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  className={conversation.id === activeConversationId ? "active" : ""}
                  onClick={() => void handleLoadConversation(conversation.id)}
                  type="button"
                >
                  <History size={15} />
                  <span>{conversation.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <details className="rail-foldout">
          <summary>
            <CalendarRange size={15} />
            快捷对照
          </summary>
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
        </details>

        <div className="rail-footer">
          <Link className="rail-action subtle" to="/admin">
            <Database size={17} />
            数据管理台
          </Link>
        </div>
      </aside>

      <section className="chat-surface">
        <header className="chat-header">
          <button className="icon-button" aria-label="toggle sidebar">
            <PanelLeft size={19} />
          </button>
          <div>
            <p className="eyebrow">Timeline conversation</p>
            <h1>{headerTitle}</h1>
          </div>
          <div className="header-status">
            <Sparkles size={16} />
            <span>{activeConversationId ? "已保存到聊天记录" : "临时会话"}</span>
          </div>
        </header>

        <div className="message-list">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onConfirm={() => void handleConfirmRun(message.id)}
            />
          ))}
          <div ref={bottomRef} />
        </div>

        <section className="composer">
          {!stickToBottom && (
            <button className="jump-latest" type="button" onClick={scrollToLatest}>
              回到最新
            </button>
          )}
          <div className="composer-inner">
            <textarea
              ref={composerRef}
              value={question}
              onChange={(event) => {
                setQuestion(event.target.value);
                requestAnimationFrame(resizeComposer);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleAsk();
                }
                if (event.key === "Escape" && question) {
                  event.preventDefault();
                  setQuestion("");
                  requestAnimationFrame(resizeComposer);
                }
                if (event.key === "ArrowUp" && !question.trim()) {
                  event.preventDefault();
                  setQuestion(lastQuestionRef.current);
                  requestAnimationFrame(resizeComposer);
                }
              }}
              rows={2}
              placeholder="输入一个历史时间点或问题，例如：公元750年前后各地区发生了什么？"
            />
            <button
              className={`send-button ${isAsking ? "stop" : ""}`}
              onClick={isAsking ? () => void handleStop() : handleAsk}
              disabled={!isAsking && !question.trim()}
              aria-label={isAsking ? "停止生成" : "发送"}
            >
              {isAsking ? <Square size={16} /> : <ArrowUp size={19} />}
            </button>
          </div>
        </section>
      </section>
    </div>
  );
}

function AuthScreen({
  authMode,
  authForm,
  authError,
  authLoading,
  onModeChange,
  onFormChange,
  onSubmit,
}: {
  authMode: "login" | "register";
  authForm: { username: string; password: string };
  authError: string;
  authLoading: boolean;
  onModeChange: (mode: "login" | "register") => void;
  onFormChange: (form: { username: string; password: string }) => void;
  onSubmit: () => void;
}) {
  const isLogin = authMode === "login";

  return (
    <section className="auth-screen">
      <div className="auth-shell">
        <div className="auth-copy">
          <div className="brand-mark auth-brand">
            <div className="brand-symbol">
              <Globe2 size={23} />
            </div>
            <div>
              <strong>历史时间对照 Agent</strong>
              <span>账号、聊天记录和长期记忆的入口</span>
            </div>
          </div>
          <h1>把每次研究保存下来。</h1>
          <p>
            登录后，聊天会绑定到你的账号；后续的聊天组、记录检索和 AI memory 都会从这里开始。
          </p>
        </div>

        <form
          className="auth-card"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <div className="auth-tabs">
            <button
              className={isLogin ? "active" : ""}
              onClick={() => onModeChange("login")}
              type="button"
            >
              登录
            </button>
            <button
              className={!isLogin ? "active" : ""}
              onClick={() => onModeChange("register")}
              type="button"
            >
              注册
            </button>
          </div>

          <label className="auth-field">
            用户名
            <input
              autoComplete="username"
              autoFocus
              value={authForm.username}
              onChange={(event) => onFormChange({ ...authForm, username: event.target.value })}
              placeholder="输入用户名"
            />
          </label>
          <label className="auth-field">
            密码
            <input
              autoComplete={isLogin ? "current-password" : "new-password"}
              type="password"
              value={authForm.password}
              onChange={(event) => onFormChange({ ...authForm, password: event.target.value })}
              placeholder="输入密码"
            />
          </label>

          {authError && <div className="auth-error">{authError}</div>}

          <button
            className="rail-action primary auth-submit"
            disabled={authLoading || !authForm.username.trim() || !authForm.password}
            type="submit"
          >
            {authLoading ? <Loader2 className="spin" size={17} /> : <LogIn size={17} />}
            {isLogin ? "登录并进入聊天" : "注册并进入聊天"}
          </button>
        </form>
      </div>
    </section>
  );
}

function MessageBubble({
  message,
  onConfirm,
}: {
  message: ChatMessage;
  onConfirm: () => void;
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
              <span>{message.phase || "正在生成..."}</span>
            </div>
          )}
          {message.status === "confirming" && (
            <div className="streaming-line">
              <Loader2 className="spin" size={15} />
              <span>正在恢复执行...</span>
            </div>
          )}
          {message.status === "cancelled" && <div className="status-line">已停止生成</div>}
          {message.content ? (
            <MarkdownContent content={message.content} />
          ) : (
            message.status === "streaming" && <div className="typing-skeleton" />
          )}
        </div>

        {message.confirmation && (
          <section className="confirmation-panel">
            <div className="confirmation-copy">
              <ShieldAlert size={18} />
              <div>
                <strong>需要确认后继续</strong>
                <span>{message.confirmation.toolName}</span>
              </div>
            </div>
            <pre>{JSON.stringify(message.confirmation.toolArguments, null, 2)}</pre>
            {message.confirmation.error && (
              <p className="confirmation-error">{message.confirmation.error}</p>
            )}
            <button
              className="primary-button confirmation-button"
              onClick={onConfirm}
              disabled={!message.runId || message.status === "confirming"}
            >
              {message.status === "confirming" ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <CheckCircle2 size={16} />
              )}
              确认并继续执行
            </button>
          </section>
        )}

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
            <summary>
              <span>执行过程</span>
              {message.runId && <small>{message.runId}</small>}
            </summary>
            {steps.map((step, index) => (
              <div className="trace-line" key={`${step.event}-${index}`}>
                <span>{step.event}</span>
                <strong>{step.tool_name || step.status || step.error_message || "message"}</strong>
              </div>
            ))}
          </details>
        )}
      </div>
    </article>
  );
}

function MarkdownContent({ content }: { content: string }) {
  const lines = content.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(<pre key={`code-${index}`} className="markdown-code">{code.join("\n")}</pre>);
      continue;
    }

    if (/^\|.+\|$/.test(line) && index + 1 < lines.length && /^\|[\s:-]+\|/.test(lines[index + 1])) {
      const tableLines = [line];
      index += 2;
      while (index < lines.length && /^\|.+\|$/.test(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      const rows = tableLines.map((row) =>
        row
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((cell) => cell.trim()),
      );
      const [head, ...body] = rows;
      blocks.push(
        <div className="markdown-table-wrap" key={`table-${index}`}>
          <table>
            <thead>
              <tr>{head.map((cell, cellIndex) => <th key={cellIndex}>{renderInline(cell)}</th>)}</tr>
            </thead>
            <tbody>
              {body.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => <td key={cellIndex}>{renderInline(cell)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^#{1,3}\s+/.test(line)) {
      const level = line.match(/^#+/)?.[0].length || 2;
      const text = line.replace(/^#{1,3}\s+/, "");
      blocks.push(
        <h3 className={`markdown-heading level-${level}`} key={`heading-${index}`}>
          {renderInline(text)}
        </h3>,
      );
      index += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={`quote-${index}`}>{renderInline(quote.join("\n"))}</blockquote>);
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={`ul-${index}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={`ol-${index}`}>
          {items.map((item, itemIndex) => <li key={itemIndex}>{renderInline(item)}</li>)}
        </ol>,
      );
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(```|#{1,3}\s+|>\s?|[-*]\s+|\d+\.\s+|\|.+\|$)/.test(lines[index])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(<p key={`p-${index}`}>{renderInline(paragraph.join("\n"))}</p>);
  }

  return <div className="markdown-content">{blocks}</div>;
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return (
      <Fragment key={index}>
        {part.split("\n").map((line, lineIndex, arr) => (
          <Fragment key={lineIndex}>
            {line}
            {lineIndex < arr.length - 1 && <br />}
          </Fragment>
        ))}
      </Fragment>
    );
  });
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

function welcomeMessage(): ChatMessage {
  return {
    id: "welcome",
    role: "assistant",
    status: "done",
    content:
      "你可以问一个历史时间点，我会尽量把同一时期不同地区发生的事情放在一起比较。登录后，聊天会自动保存到你的历史记录里。",
  };
}

function messagesFromStored(storedMessages: StoredChatMessage[]): ChatMessage[] {
  if (!storedMessages.length) return [welcomeMessage()];
  return storedMessages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      id: message.id,
      role: message.role === "user" ? "user" : "assistant",
      content: message.content,
      status: message.status,
      runId: message.agent_run_id || undefined,
      events: message.artifacts?.event || [],
      references: message.artifacts?.reference || [],
      links: message.artifacts?.link || [],
      steps: [],
    }));
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

function describeStreamEvent(event: AgentStreamEvent) {
  if (event.event === "run_started") return "正在建立研究任务...";
  if (event.event === "step_started") return `准备调用 ${event.tool_name || "工具"}...`;
  if (event.event === "tool_called") return `正在查询 ${event.tool_name || "历史资料"}...`;
  if (event.event === "tool_result") return `${event.tool_name || "工具"} 已返回，正在整理证据...`;
  if (event.event === "answer_delta") return "正在生成回答...";
  if (event.event === "final_answer") return "回答完成";
  if (event.event === "confirmation_required") return "等待人工确认";
  if (event.event === "run_failed") return "运行失败";
  if (event.event === "run_cancelled") return "已停止";
  return "正在推进任务...";
}
