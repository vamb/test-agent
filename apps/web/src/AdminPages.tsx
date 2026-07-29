import { ReactNode, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Archive,
  ArrowLeft,
  CheckCircle2,
  Database,
  Edit3,
  FileSearch,
  FileText,
  GitBranch,
  Home,
  Layers3,
  Loader2,
  RefreshCcw,
  Save,
  Search,
  ShieldAlert,
  Trash2,
  Upload,
} from "lucide-react";
import {
  AdminEventDetail,
  AdminEventListItem,
  AdminOverview,
  AdminRelation,
  AdminSource,
  ImportBatch,
  ImportBatchReview,
  KnowledgeDocument,
  StagingRow,
  VectorJob,
  adminApi,
} from "./adminApi";

type LoadState = "idle" | "loading" | "error" | "done";

const sampleImport = JSON.stringify(
  {
    events: [
      {
        title: "测试导入事件",
        start_year: 912,
        end_year: 912,
        start_date_text: "912年",
        end_date_text: "912年",
        time_precision: "year",
        region: "测试地区",
        polity: "测试政权",
        modern_country: "测试国",
        category: ["测试分类"],
        summary: "用于管理后台导入工作台验证的事件。",
        causes: ["测试原因"],
        effects: ["测试影响"],
        actors: ["测试人物"],
        source_status: "draft",
        confidence: 0.8,
        sources: [
          {
            source_title: "测试来源",
            source_type: "note",
            citation: "测试引用",
            excerpt: "测试摘录",
            reliability: 0.8,
          },
        ],
      },
    ],
  },
  null,
  2,
);

const adminNav = [
  { to: "/admin", label: "总览", icon: Home, end: true },
  { to: "/admin/imports", label: "导入审核", icon: Upload },
  { to: "/admin/events", label: "事件库", icon: Database },
  { to: "/admin/quality", label: "数据质量", icon: ShieldAlert },
  { to: "/admin/relations", label: "关系", icon: GitBranch },
  { to: "/admin/knowledge", label: "知识库", icon: FileText },
  { to: "/admin/vectors", label: "向量", icon: Layers3 },
];

type EventFormState = {
  title: string;
  summary: string;
  confidence: string;
  source_status: string;
  category: string;
  causes: string;
  effects: string;
};

type SourceFormState = {
  source_title: string;
  source_type: string;
  url: string;
  citation: string;
  excerpt: string;
  reliability: string;
  is_primary: boolean;
};

type RelationFormState = {
  source_event_id: string;
  target_event_id: string;
  relation_type: string;
  explanation: string;
  confidence: string;
};

type DocumentFormState = {
  title: string;
  source_type: string;
  source_uri: string;
  citation: string;
  status: string;
};

export function AdminLayout() {
  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <Link className="admin-brand" to="/">
          <ArrowLeft size={17} />
          返回聊天
        </Link>
        <div className="admin-title">
          <span>Archive Ops</span>
          <strong>历史数据管理台</strong>
        </div>
        <nav className="admin-nav">
          {adminNav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                <Icon size={17} />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <section className="admin-main">
        <Outlet />
      </section>
    </div>
  );
}

export function AdminOverviewPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [overview, setOverview] = useState<AdminOverview>({});
  const [vectors, setVectors] = useState<Record<string, unknown>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    setState("loading");
    Promise.all([adminApi.getOverview(), adminApi.getVectorStatus()])
      .then(([overviewResult, vectorResult]) => {
        setOverview(overviewResult);
        setVectors(vectorResult);
        setState("done");
      })
      .catch((err) => {
        setError(readError(err));
        setState("error");
      });
  }, []);

  return (
    <AdminPageShell
      eyebrow="Management overview"
      title="后台总览"
      description="只展示数据资产、知识库和向量运营状态；Agent 运行分析后续跳转 Langfuse。"
      state={state}
      error={error}
    >
      <div className="metric-grid">
        <MetricCard title="事件总数" value={metric(overview.events, "total_events")} />
        <MetricCard title="低置信事件" value={metric(overview.events, "low_confidence_events")} tone="warn" />
        <MetricCard title="待审核批次" value={metric(overview.imports, "pending_batches")} />
        <MetricCard title="知识文档" value={metric(overview.knowledge, "documents")} />
        <MetricCard title="事件向量覆盖" value={percentFrom(vectors, "event_embedding_coverage")} />
        <MetricCard title="知识向量覆盖" value={percentFrom(vectors, "knowledge_embedding_coverage")} />
      </div>

      <div className="admin-two-col">
        <section className="admin-panel">
          <PanelTitle icon={<Upload size={18} />} title="下一批数据运营" />
          <div className="action-stack">
            <Link className="admin-action" to="/admin/imports/new">粘贴 JSON/CSV 创建导入批次</Link>
            <Link className="admin-action" to="/admin/imports">处理 staging 错误和重复候选</Link>
            <Link className="admin-action" to="/admin/quality">查看数据质量问题</Link>
          </div>
        </section>
        <section className="admin-panel">
          <PanelTitle icon={<Layers3 size={18} />} title="向量健康" />
          <JsonBlock value={vectors} compact />
        </section>
      </div>
    </AdminPageShell>
  );
}

export function AdminImportsPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  function load() {
    setState("loading");
    adminApi
      .listBatches({ status, limit: 50 })
      .then((result) => {
        setBatches(result.batches || []);
        setState("done");
      })
      .catch((err) => {
        setError(readError(err));
        setState("error");
      });
  }

  useEffect(load, [status]);

  return (
    <AdminPageShell
      eyebrow="Import review"
      title="导入批次"
      description="查看导入批次、进入 staging 审核，处理错误行和重复候选。"
      state={state}
      error={error}
      action={<Link className="primary-button" to="/admin/imports/new"><Upload size={16} /> 新建导入</Link>}
    >
      <div className="admin-toolbar">
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">全部状态</option>
          <option value="pending">pending</option>
          <option value="validated">validated</option>
          <option value="imported">imported</option>
          <option value="rejected">rejected</option>
        </select>
        <button className="ghost-button" onClick={load}><RefreshCcw size={16} /> 刷新</button>
      </div>

      <div className="admin-table">
        <div className="admin-table-head import-grid">
          <span>文件</span><span>状态</span><span>行数</span><span>创建者</span><span>操作</span>
        </div>
        {batches.map((batch) => (
          <div className="admin-table-row import-grid" key={batch.id}>
            <strong>{batch.filename}</strong>
            <StatusPill value={batch.status} />
            <span>{batch.valid_rows}/{batch.total_rows} valid，{batch.error_rows} error</span>
            <span>{batch.created_by || "-"}</span>
            <Link to={`/admin/imports/${batch.id}`}>审核</Link>
          </div>
        ))}
      </div>
      {!batches.length && state === "done" && <EmptyState text="还没有匹配的导入批次。" />}
    </AdminPageShell>
  );
}

export function AdminImportCreatePage() {
  const navigate = useNavigate();
  const [format, setFormat] = useState<"json" | "csv">("json");
  const [content, setContent] = useState(sampleImport);
  const [filename, setFilename] = useState("manual-import.json");
  const [parseResult, setParseResult] = useState<Record<string, unknown> | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState("");

  async function parse() {
    setState("loading");
    setError("");
    try {
      const result = await adminApi.parseImport(content, format);
      setParseResult(result);
      setState("done");
    } catch (err) {
      setError(readError(err));
      setState("error");
    }
  }

  async function createBatch() {
    const events = parseResult?.events;
    if (!Array.isArray(events) || !events.length) return;
    setState("loading");
    try {
      const batch = await adminApi.createBatch({
        filename,
        source_note: "web-admin",
        created_by: "web-admin",
        events,
      });
      navigate(`/admin/imports/${batch.id}`);
    } catch (err) {
      setError(readError(err));
      setState("error");
    }
  }

  return (
    <AdminPageShell
      eyebrow="New import"
      title="数据导入工作台"
      description="粘贴标准 JSON 或 CSV，先解析校验，再创建导入批次。"
      state={state === "loading" ? "loading" : "idle"}
      error={error}
    >
      <div className="admin-two-col wide-left">
        <section className="admin-panel">
          <PanelTitle icon={<Upload size={18} />} title="导入内容" />
          <div className="admin-form-grid">
            <label>文件名<input value={filename} onChange={(event) => setFilename(event.target.value)} /></label>
            <label>格式<select value={format} onChange={(event) => setFormat(event.target.value as "json" | "csv")}>
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select></label>
          </div>
          <textarea className="code-input" value={content} onChange={(event) => setContent(event.target.value)} />
          <div className="button-row">
            <button className="primary-button" onClick={parse}><FileSearch size={16} /> 解析预览</button>
            <button className="ghost-button" onClick={createBatch} disabled={!Array.isArray(parseResult?.events)}>
              <CheckCircle2 size={16} /> 创建批次
            </button>
          </div>
        </section>
        <section className="admin-panel">
          <PanelTitle icon={<FileSearch size={18} />} title="解析结果" />
          {parseResult ? <JsonBlock value={parseResult} /> : <EmptyState text="解析后会在这里显示行数、错误和标准 events payload。" />}
        </section>
      </div>
    </AdminPageShell>
  );
}

export function AdminImportDetailPage() {
  const { batchId = "" } = useParams();
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [review, setReview] = useState<ImportBatchReview | null>(null);
  const [rows, setRows] = useState<StagingRow[]>([]);
  const [selected, setSelected] = useState<StagingRow | null>(null);
  const [editor, setEditor] = useState("");
  const [message, setMessage] = useState("");
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");

  function load() {
    setState("loading");
    Promise.all([adminApi.getBatch(batchId), adminApi.previewBatch(batchId), adminApi.getBatchReview(batchId)])
      .then(([batchResult, preview, reviewResult]) => {
        setBatch(batchResult);
        setReview(reviewResult);
        setRows(preview.rows || []);
        setSelected((current) => current ? (preview.rows || []).find((row) => row.id === current.id) || null : (preview.rows || [])[0] || null);
        setState("done");
      })
      .catch((err) => {
        setError(readError(err));
        setState("error");
      });
  }

  useEffect(load, [batchId]);

  useEffect(() => {
    setEditor(selected ? JSON.stringify(selected.raw_payload, null, 2) : "");
  }, [selected]);

  async function saveRow() {
    if (!selected) return;
    try {
      await adminApi.updateStagingRow(selected.id, JSON.parse(editor) as Record<string, unknown>);
      setMessage("staging 行已保存并重新校验。");
      load();
    } catch (err) {
      setMessage(readError(err));
    }
  }

  async function mergeRow(strategy: string) {
    const target = selected?.duplicate_candidates?.[0]?.id;
    if (!selected || !target) return;
    await adminApi.mergeStagingRow(selected.id, strategy, target);
    setMessage(`已执行合并策略：${strategy}`);
    load();
  }

  async function batchAction(action: "confirm" | "reject" | "revalidate") {
    if (action === "confirm") await adminApi.confirmBatch(batchId);
    if (action === "reject") await adminApi.rejectBatch(batchId, "Rejected in web admin");
    if (action === "revalidate") await adminApi.bulkRevalidateStaging(batchId);
    setMessage(`批次操作完成：${action}`);
    load();
  }

  return (
    <AdminPageShell
      eyebrow="Staging review"
      title={batch?.filename || "导入审核详情"}
      description="逐行检查 staging payload，处理校验错误和重复候选。"
      state={state}
      error={error}
      action={<div className="button-row tight">
        <Link className="ghost-button" to={`/admin/events?import_batch_id=${encodeURIComponent(batchId)}`}><Database size={16} /> 查看入库事件</Link>
        <button className="ghost-button" onClick={() => void batchAction("revalidate")}><RefreshCcw size={16} /> 重校验</button>
        <button className="primary-button" onClick={() => void batchAction("confirm")}><CheckCircle2 size={16} /> 确认入库</button>
        <button className="danger-button" onClick={() => void batchAction("reject")}><Archive size={16} /> 拒绝</button>
      </div>}
    >
      {message && <div className="notice-line">{message}</div>}
      {review?.found && (
        <section className="admin-panel batch-review-panel">
          <PanelTitle icon={<ShieldAlert size={18} />} title="入库批次核验" />
          <div className="metric-grid compact">
            <MetricCard title="本批事件" value={review.count ?? 0} />
            <MetricCard title="低置信" value={review.review?.low_confidence_count ?? 0} tone="warn" />
            <MetricCard title="弱来源" value={review.review?.weak_source_count ?? 0} tone="warn" />
            <MetricCard title="重复候选" value={review.review?.duplicate_candidate_count ?? 0} tone="warn" />
            <MetricCard title="结构缺口" value={review.review?.empty_structure_count ?? 0} />
          </div>
          <div className="button-row">
            <Link className="ghost-button" to={`/admin/events?import_batch_id=${encodeURIComponent(batchId)}`}>
              <Database size={16} /> 查看本批事件
            </Link>
            <Link className="ghost-button" to="/admin/quality">
              <ShieldAlert size={16} /> 打开数据质量
            </Link>
          </div>
          {Boolean(review.review?.duplicate_candidate_count) && (
            <JsonBlock value={{ duplicate_candidates: review.issues?.duplicate_candidates }} compact />
          )}
        </section>
      )}
      <div className="admin-two-col">
        <section className="admin-panel">
          <PanelTitle icon={<Database size={18} />} title={`Staging rows ${rows.length}`} />
          <div className="row-list">
            {rows.map((row) => (
              <button
                className={selected?.id === row.id ? "active" : ""}
                key={row.id}
                onClick={() => setSelected(row)}
              >
                <span>#{row.row_number} {String(row.raw_payload.title || "未命名事件")}</span>
                <StatusPill value={row.status} />
                {row.has_duplicate_candidates && <small>duplicate</small>}
              </button>
            ))}
          </div>
        </section>
        <section className="admin-panel">
          <PanelTitle icon={<Save size={18} />} title="行编辑和冲突处理" />
          {selected ? (
            <>
              <textarea className="code-input short" value={editor} onChange={(event) => setEditor(event.target.value)} />
              <div className="button-row">
                <button className="primary-button" onClick={saveRow}><Save size={16} /> 保存行</button>
                <button className="ghost-button" onClick={() => void mergeRow("merge_sources_and_categories")} disabled={!selected.has_duplicate_candidates}>
                  合并来源和分类
                </button>
                <button className="ghost-button" onClick={() => void mergeRow("replace_existing")} disabled={!selected.has_duplicate_candidates}>
                  替换已有事件
                </button>
              </div>
              {(selected.validation_errors || []).length > 0 && (
                <div className="error-list">{selected.validation_errors?.map((item) => <span key={item}>{item}</span>)}</div>
              )}
              {selected.has_duplicate_candidates && <JsonBlock value={{ duplicate_candidates: selected.duplicate_candidates, field_differences: selected.field_differences }} compact />}
            </>
          ) : (
            <EmptyState text="选择一行 staging 数据后编辑。" />
          )}
        </section>
      </div>
    </AdminPageShell>
  );
}

export function AdminEventsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [importBatchId, setImportBatchId] = useState(searchParams.get("import_batch_id") || "");
  const [startYear, setStartYear] = useState("");
  const [endYear, setEndYear] = useState("");
  const [minConfidence, setMinConfidence] = useState("");
  const [hasSources, setHasSources] = useState("");
  const [regions, setRegions] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [events, setEvents] = useState<AdminEventListItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");

  function load() {
    setState("loading");
    adminApi.listEvents({
      query,
      regions: region ? [region] : undefined,
      statuses: statusFilter ? [statusFilter] : undefined,
      import_batch_id: importBatchId || undefined,
      start_year: startYear || undefined,
      end_year: endYear || undefined,
      min_confidence: minConfidence || undefined,
      has_sources: hasSources || undefined,
      limit: 50,
    })
      .then((result) => {
        setEvents(result.events || []);
        setState("done");
      })
      .catch((err) => {
        setError(readError(err));
        setState("error");
      });
  }

  useEffect(() => {
    adminApi.getDictionaries().then((result) => {
      setRegions(result.regions || []);
      setStatuses(result.event_statuses || []);
    });
    load();
  }, []);

  async function bulkArchive() {
    await adminApi.bulkUpdateEvents(selected, { status: "archived" });
    setSelected([]);
    load();
  }

  function search() {
    const nextParams = new URLSearchParams(searchParams);
    if (importBatchId) {
      nextParams.set("import_batch_id", importBatchId);
    } else {
      nextParams.delete("import_batch_id");
    }
    setSearchParams(nextParams, { replace: true });
    load();
  }

  return (
    <AdminPageShell eyebrow="Event library" title="事件库" description="搜索、筛选和批量维护历史事件。" state={state} error={error}>
      <div className="admin-toolbar">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、摘要、地区或政权" />
        <input value={importBatchId} onChange={(event) => setImportBatchId(event.target.value)} placeholder="导入批次 ID" />
        <input value={startYear} onChange={(event) => setStartYear(event.target.value)} placeholder="开始年份" type="number" />
        <input value={endYear} onChange={(event) => setEndYear(event.target.value)} placeholder="结束年份" type="number" />
        <select value={region} onChange={(event) => setRegion(event.target.value)}>
          <option value="">全部地区</option>
          {regions.map((item) => <option value={item} key={item}>{item}</option>)}
        </select>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="">全部状态</option>
          {statuses.map((item) => <option value={item} key={item}>{item}</option>)}
        </select>
        <input value={minConfidence} onChange={(event) => setMinConfidence(event.target.value)} placeholder="最低置信度" type="number" min="0" max="1" step="0.1" />
        <select value={hasSources} onChange={(event) => setHasSources(event.target.value)}>
          <option value="">来源不限</option>
          <option value="true">有来源</option>
          <option value="false">无来源</option>
        </select>
        <button className="primary-button" onClick={search}><Search size={16} /> 搜索</button>
        <button className="ghost-button" onClick={bulkArchive} disabled={!selected.length}><Archive size={16} /> 批量归档</button>
      </div>
      <div className="admin-table">
        <div className="admin-table-head events-grid"><span></span><span>事件</span><span>时间</span><span>地区</span><span>状态</span><span>来源</span></div>
        {events.map((event) => (
          <div className="admin-table-row events-grid" key={event.id}>
            <input
              type="checkbox"
              checked={selected.includes(event.id)}
              onChange={(inputEvent) => setSelected((current) => inputEvent.target.checked ? [...current, event.id] : current.filter((id) => id !== event.id))}
            />
            <Link to={`/admin/events/${event.id}`}><strong>{event.title}</strong><small>{event.summary || ""}</small></Link>
            <span>{event.start_year}-{event.end_year || event.start_year}</span>
            <span>{event.region || "-"}</span>
            <StatusPill value={event.source_status || event.status || "draft"} />
            <span>{event.source_count ?? "-"}</span>
          </div>
        ))}
      </div>
    </AdminPageShell>
  );
}

export function AdminEventDetailPage() {
  const { eventId = "" } = useParams();
  const [detail, setDetail] = useState<AdminEventDetail | null>(null);
  const [form, setForm] = useState<EventFormState>({
    title: "",
    summary: "",
    confidence: "0.5",
    source_status: "draft",
    category: "",
    causes: "",
    effects: "",
  });
  const [sourceForm, setSourceForm] = useState<SourceFormState>({
    source_title: "",
    source_type: "note",
    url: "",
    citation: "",
    excerpt: "",
    reliability: "0.7",
    is_primary: false,
  });
  const [editingSourceId, setEditingSourceId] = useState("");
  const [message, setMessage] = useState("");
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const event = detail?.event;

  function load() {
    setState("loading");
    adminApi.getEventDetail(eventId)
      .then((result) => {
        setDetail(result);
        setForm({
          title: result.event?.title || "",
          summary: result.event?.summary || "",
          confidence: String(result.event?.confidence ?? 0.5),
          source_status: result.event?.source_status || result.event?.status || "draft",
          category: (result.event?.category || []).join("；"),
          causes: (result.event?.causes || []).join("；"),
          effects: (result.event?.effects || []).join("；"),
        });
        setState("done");
      })
      .catch((err) => {
        setError(readError(err));
        setState("error");
      });
  }

  useEffect(load, [eventId]);

  async function save() {
    await adminApi.updateEvent(eventId, {
      title: form.title,
      summary: form.summary,
      confidence: Number(form.confidence || 0),
      source_status: form.source_status,
      category: splitList(form.category),
      causes: splitList(form.causes),
      effects: splitList(form.effects),
    });
    setMessage("事件字段已保存。");
    load();
  }

  async function addSource() {
    const payload = sourceFormToPayload(sourceForm);
    if (editingSourceId) {
      await adminApi.updateSource(editingSourceId, payload);
      setMessage("来源已更新。");
    } else {
      await adminApi.addSource(eventId, payload);
      setMessage("来源已新增。");
    }
    resetSourceForm();
    load();
  }

  function editSource(source: AdminSource) {
    setEditingSourceId(source.id);
    setSourceForm({
      source_title: source.source_title || "",
      source_type: source.source_type || "note",
      url: source.url || "",
      citation: source.citation || "",
      excerpt: source.excerpt || "",
      reliability: String(source.reliability ?? 0.5),
      is_primary: Boolean(source.is_primary),
    });
  }

  function resetSourceForm() {
    setEditingSourceId("");
    setSourceForm({
      source_title: "",
      source_type: "note",
      url: "",
      citation: "",
      excerpt: "",
      reliability: "0.7",
      is_primary: false,
    });
  }

  async function deleteSource(sourceId: string) {
    await adminApi.deleteSource(sourceId);
    setMessage("来源已删除。");
    load();
  }

  return (
    <AdminPageShell eyebrow="Event detail" title={event?.title || "事件详情"} description="编辑事件字段，维护来源、关系和审计记录。" state={state} error={error}>
      {message && <div className="notice-line">{message}</div>}
      <div className="admin-two-col wide-left">
        <section className="admin-panel">
          <PanelTitle icon={<Save size={18} />} title="事件字段" />
          <div className="admin-form-grid event-edit-grid">
            <label>标题<input value={form.title} onChange={(input) => setForm({ ...form, title: input.target.value })} /></label>
            <label>状态<select value={form.source_status} onChange={(input) => setForm({ ...form, source_status: input.target.value })}>
              <option value="draft">draft</option>
              <option value="reviewing">reviewing</option>
              <option value="verified">verified</option>
              <option value="disputed">disputed</option>
              <option value="archived">archived</option>
            </select></label>
            <label>置信度<input type="number" min="0" max="1" step="0.05" value={form.confidence} onChange={(input) => setForm({ ...form, confidence: input.target.value })} /></label>
            <label className="span-2">分类<input value={form.category} onChange={(input) => setForm({ ...form, category: input.target.value })} placeholder="多个值用；分隔" /></label>
            <label className="span-2">摘要<textarea value={form.summary} onChange={(input) => setForm({ ...form, summary: input.target.value })} rows={5} /></label>
            <label className="span-2">前因<input value={form.causes} onChange={(input) => setForm({ ...form, causes: input.target.value })} placeholder="多个值用；分隔" /></label>
            <label className="span-2">影响<input value={form.effects} onChange={(input) => setForm({ ...form, effects: input.target.value })} placeholder="多个值用；分隔" /></label>
          </div>
          <button className="primary-button" onClick={save}><Save size={16} /> 保存事件</button>
        </section>
        <section className="admin-panel">
          <PanelTitle icon={<FileText size={18} />} title="来源" />
          <div className="source-mini-list">
            {(detail?.sources || []).map((source) => (
              <article key={source.id}>
                <strong>{source.source_title}</strong>
                <span>{source.source_type} / {Number(source.reliability || 0).toFixed(2)}</span>
                <div className="button-row tight">
                  <button className="ghost-button" onClick={() => editSource(source)}><Edit3 size={15} /> 编辑</button>
                  <button className="ghost-button" onClick={() => void adminApi.verifySource(source.id, 0.85).then(load)}>核验 0.85</button>
                  <button className="danger-button" onClick={() => void deleteSource(source.id)}><Trash2 size={15} /> 删除</button>
                </div>
              </article>
            ))}
          </div>
          <div className="source-form">
            <label>标题<input value={sourceForm.source_title} onChange={(input) => setSourceForm({ ...sourceForm, source_title: input.target.value })} /></label>
            <label>类型<select value={sourceForm.source_type} onChange={(input) => setSourceForm({ ...sourceForm, source_type: input.target.value })}>
              <option value="note">note</option>
              <option value="book">book</option>
              <option value="paper">paper</option>
              <option value="primary_source">primary_source</option>
              <option value="encyclopedia">encyclopedia</option>
              <option value="website">website</option>
              <option value="dataset">dataset</option>
            </select></label>
            <label>URL<input value={sourceForm.url} onChange={(input) => setSourceForm({ ...sourceForm, url: input.target.value })} /></label>
            <label>可靠度<input type="number" min="0" max="1" step="0.05" value={sourceForm.reliability} onChange={(input) => setSourceForm({ ...sourceForm, reliability: input.target.value })} /></label>
            <label className="span-2">引用<input value={sourceForm.citation} onChange={(input) => setSourceForm({ ...sourceForm, citation: input.target.value })} /></label>
            <label className="span-2">摘录<textarea rows={4} value={sourceForm.excerpt} onChange={(input) => setSourceForm({ ...sourceForm, excerpt: input.target.value })} /></label>
            <label className="check-label"><input type="checkbox" checked={sourceForm.is_primary} onChange={(input) => setSourceForm({ ...sourceForm, is_primary: input.target.checked })} /> 主要来源</label>
          </div>
          <div className="button-row">
            <button className="ghost-button" onClick={addSource}>{editingSourceId ? "保存来源" : "新增来源"}</button>
            {editingSourceId && <button className="ghost-button" onClick={resetSourceForm}>取消编辑</button>}
          </div>
        </section>
      </div>
      <div className="admin-two-col">
        <section className="admin-panel"><PanelTitle icon={<GitBranch size={18} />} title="关系" /><JsonBlock value={detail?.relations || []} compact /></section>
        <section className="admin-panel"><PanelTitle icon={<Archive size={18} />} title="审计" /><JsonBlock value={detail?.changes || []} compact /></section>
      </div>
    </AdminPageShell>
  );
}

export function AdminRelationsPage() {
  const [relations, setRelations] = useState<AdminRelation[]>([]);
  const [editingRelationId, setEditingRelationId] = useState("");
  const [form, setForm] = useState<RelationFormState>({
    source_event_id: "",
    target_event_id: "",
    relation_type: "contemporary",
    explanation: "",
    confidence: "0.5",
  });
  const [message, setMessage] = useState("");
  const [state, setState] = useState<LoadState>("loading");

  function load() {
    setState("loading");
    adminApi.listRelations({ limit: 50 }).then((result) => {
      setRelations(result.relations || []);
      setState("done");
    });
  }

  useEffect(load, []);

  async function create() {
    const payload = relationFormToPayload(form);
    if (editingRelationId) {
      await adminApi.updateRelation(editingRelationId, {
        relation_type: payload.relation_type,
        explanation: payload.explanation,
        confidence: payload.confidence,
      });
      setMessage("关系已更新。");
    } else {
      await adminApi.createRelation(payload);
      setMessage("关系已创建。");
    }
    resetRelationForm();
    load();
  }

  function editRelation(relation: AdminRelation) {
    setEditingRelationId(relation.id);
    setForm({
      source_event_id: relation.source_event_id,
      target_event_id: relation.target_event_id,
      relation_type: relation.relation_type,
      explanation: relation.explanation || "",
      confidence: String(relation.confidence ?? 0.5),
    });
  }

  function resetRelationForm() {
    setEditingRelationId("");
    setForm({
      source_event_id: "",
      target_event_id: "",
      relation_type: "contemporary",
      explanation: "",
      confidence: "0.5",
    });
  }

  async function deleteRelation(relationId: string) {
    await adminApi.deleteRelation(relationId);
    setMessage("关系已删除。");
    load();
  }

  return (
    <AdminPageShell eyebrow="Relations" title="关系管理" description="维护事件之间的同期、因果、影响和不确定关系。" state={state}>
      {message && <div className="notice-line">{message}</div>}
      <div className="admin-two-col">
        <section className="admin-panel">
          <PanelTitle icon={<GitBranch size={18} />} title="关系列表" />
          <div className="relation-list">
            {relations.map((relation) => (
              <article key={relation.id}>
                <span>{relation.relation_type} / {Number(relation.confidence || 0).toFixed(2)}</span>
                <strong>{relation.source_event_title || relation.source_event_id}</strong>
                <p>{relation.target_event_title || relation.target_event_id}</p>
                <small>{relation.explanation || "暂无说明"}</small>
                <div className="button-row tight">
                  <button className="ghost-button" onClick={() => editRelation(relation)}><Edit3 size={15} /> 编辑</button>
                  <button className="danger-button" onClick={() => void deleteRelation(relation.id)}><Trash2 size={15} /> 删除</button>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className="admin-panel">
          <PanelTitle icon={<Save size={18} />} title={editingRelationId ? "编辑关系" : "新增关系"} />
          <div className="source-form">
            <label>起点事件 ID<input value={form.source_event_id} disabled={Boolean(editingRelationId)} onChange={(input) => setForm({ ...form, source_event_id: input.target.value })} /></label>
            <label>终点事件 ID<input value={form.target_event_id} disabled={Boolean(editingRelationId)} onChange={(input) => setForm({ ...form, target_event_id: input.target.value })} /></label>
            <label>关系类型<select value={form.relation_type} onChange={(input) => setForm({ ...form, relation_type: input.target.value })}>
              <option value="contemporary">contemporary</option>
              <option value="cause">cause</option>
              <option value="effect">effect</option>
              <option value="influence">influence</option>
              <option value="trade_link">trade_link</option>
              <option value="conflict_link">conflict_link</option>
              <option value="uncertain">uncertain</option>
            </select></label>
            <label>置信度<input type="number" min="0" max="1" step="0.05" value={form.confidence} onChange={(input) => setForm({ ...form, confidence: input.target.value })} /></label>
            <label className="span-2">说明<textarea rows={6} value={form.explanation} onChange={(input) => setForm({ ...form, explanation: input.target.value })} /></label>
          </div>
          <div className="button-row">
            <button className="primary-button" onClick={create}>{editingRelationId ? "保存关系" : "创建关系"}</button>
            {editingRelationId && <button className="ghost-button" onClick={resetRelationForm}>取消编辑</button>}
          </div>
        </section>
      </div>
    </AdminPageShell>
  );
}

export function AdminQualityPage() {
  const [summary, setSummary] = useState<Record<string, unknown>>({});
  const [issues, setIssues] = useState<Array<Record<string, unknown>>>([]);
  const [issueType, setIssueType] = useState("");
  const [state, setState] = useState<LoadState>("loading");

  function load() {
    setState("loading");
    Promise.all([adminApi.qualitySummary(), adminApi.qualityIssues({ issue_type: issueType, limit: 50 })])
      .then(([summaryResult, issueResult]) => {
        setSummary(summaryResult);
        setIssues(issueResult.issues as unknown as Array<Record<string, unknown>>);
        setState("done");
      });
  }

  useEffect(load, [issueType]);

  return (
    <AdminPageShell eyebrow="Data quality" title="数据质量修复台" description="从质量问题进入事件或关系修复。" state={state}>
      <div className="admin-toolbar">
        <select value={issueType} onChange={(event) => setIssueType(event.target.value)}>
          <option value="">全部问题</option>
          <option value="missing_source">missing_source</option>
          <option value="low_confidence">low_confidence</option>
          <option value="duplicate_event">duplicate_event</option>
          <option value="duplicate_title">duplicate_title</option>
          <option value="relation_missing_evidence">relation_missing_evidence</option>
        </select>
      </div>
      <div className="admin-two-col">
        <section className="admin-panel"><PanelTitle icon={<ShieldAlert size={18} />} title="问题摘要" /><JsonBlock value={summary} compact /></section>
        <section className="admin-panel"><PanelTitle icon={<FileSearch size={18} />} title="问题列表" /><div className="issue-list">{issues.map((issue, index) => <QualityIssue key={`${String(issue.target_id)}-${index}`} issue={issue} />)}</div></section>
      </div>
    </AdminPageShell>
  );
}

export function AdminKnowledgePage() {
  const [documents, setDocuments] = useState<Array<Record<string, unknown>>>([]);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    adminApi.listDocuments({ limit: 50 }).then((result) => {
      setDocuments(result.documents as unknown as Array<Record<string, unknown>>);
      setState("done");
    });
  }, []);

  return (
    <AdminPageShell eyebrow="Knowledge base" title="知识库管理" description="查看知识文档、chunk 和 reembed 入口。" state={state}>
      <div className="admin-table">
        <div className="admin-table-head knowledge-grid"><span>标题</span><span>状态</span><span>chunk</span><span>操作</span></div>
        {documents.map((doc) => (
          <div className="admin-table-row knowledge-grid" key={String(doc.id)}>
            <strong>{String(doc.title)}</strong>
            <StatusPill value={String(doc.status || "active")} />
            <span>{String(doc.chunk_count ?? "-")}</span>
            <Link to={`/admin/knowledge/${String(doc.id)}`}>查看</Link>
          </div>
        ))}
      </div>
    </AdminPageShell>
  );
}

export function AdminKnowledgeDetailPage() {
  const { documentId = "" } = useParams();
  const [document, setDocument] = useState<KnowledgeDocument | null>(null);
  const [form, setForm] = useState<DocumentFormState>({
    title: "",
    source_type: "note",
    source_uri: "",
    citation: "",
    status: "active",
  });
  const [chunks, setChunks] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("");
  const [state, setState] = useState<LoadState>("loading");

  function load() {
    setState("loading");
    adminApi.getDocumentChunks(documentId).then((result) => {
      setDocument(result.document || null);
      setForm({
        title: result.document?.title || "",
        source_type: result.document?.source_type || "note",
        source_uri: result.document?.source_uri || "",
        citation: result.document?.citation || "",
        status: result.document?.status || "active",
      });
      setChunks(result.chunks || []);
      setState("done");
    });
  }

  useEffect(load, [documentId]);

  async function saveDocument(updates?: Record<string, unknown>) {
    await adminApi.updateDocument(documentId, updates || {
      title: form.title,
      source_type: form.source_type,
      source_uri: form.source_uri,
      citation: form.citation,
      status: form.status,
    });
    setMessage("知识文档已更新。");
    load();
  }

  return (
    <AdminPageShell eyebrow="Document chunks" title={document?.title || "知识文档详情"} description="查看 chunk，更新元数据，并触发文档 reembed。" state={state} action={<button className="primary-button" onClick={() => void adminApi.reembedDocument(documentId).then(load)}><RefreshCcw size={16} /> Reembed</button>}>
      {message && <div className="notice-line">{message}</div>}
      <section className="admin-panel">
        <PanelTitle icon={<FileText size={18} />} title="文档元数据" />
        <div className="source-form document-form">
          <label>标题<input value={form.title} onChange={(input) => setForm({ ...form, title: input.target.value })} /></label>
          <label>类型<select value={form.source_type} onChange={(input) => setForm({ ...form, source_type: input.target.value })}>
            <option value="note">note</option>
            <option value="book">book</option>
            <option value="paper">paper</option>
            <option value="website">website</option>
            <option value="dataset">dataset</option>
          </select></label>
          <label>状态<select value={form.status} onChange={(input) => setForm({ ...form, status: input.target.value })}>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
            <option value="archived">archived</option>
          </select></label>
          <label className="span-2">URI<input value={form.source_uri} onChange={(input) => setForm({ ...form, source_uri: input.target.value })} /></label>
          <label className="span-2">引用<textarea rows={3} value={form.citation} onChange={(input) => setForm({ ...form, citation: input.target.value })} /></label>
        </div>
        <div className="button-row">
          <button className="primary-button" onClick={() => void saveDocument()}><Save size={16} /> 保存文档</button>
          <button className="ghost-button" onClick={() => void saveDocument({ status: "inactive" })}>停用</button>
          <button className="danger-button" onClick={() => void saveDocument({ status: "archived" })}>归档</button>
        </div>
      </section>
      <div className="chunk-list">
        {chunks.map((chunk, index) => <article key={`${String(chunk.id)}-${index}`}><strong>Chunk {index + 1}</strong><p>{String(chunk.content || chunk.chunk_text || "")}</p></article>)}
      </div>
    </AdminPageShell>
  );
}

export function AdminVectorsPage() {
  const [status, setStatus] = useState<Record<string, unknown>>({});
  const [job, setJob] = useState<VectorJob | null>(null);
  const [target, setTarget] = useState("knowledge");
  const [state, setState] = useState<LoadState>("loading");

  function load() {
    setState("loading");
    adminApi.getVectorStatus().then((result) => {
      setStatus(result);
      setState("done");
    });
  }

  useEffect(load, []);

  async function createJob() {
    const result = await adminApi.createVectorJob(target);
    setJob(("job" in result ? result.job : result) as VectorJob);
  }

  async function processJob() {
    if (!job?.id) return;
    await adminApi.processVectorJob(job.id);
    load();
  }

  return (
    <AdminPageShell eyebrow="Vector operations" title="向量管理" description="查看 embedding 覆盖率，创建和处理重建任务。" state={state}>
      <div className="admin-two-col">
        <section className="admin-panel"><PanelTitle icon={<Layers3 size={18} />} title="覆盖率" /><JsonBlock value={status} /></section>
        <section className="admin-panel">
          <PanelTitle icon={<RefreshCcw size={18} />} title="重建任务" />
          <select value={target} onChange={(event) => setTarget(event.target.value)}>
            <option value="knowledge">knowledge</option>
            <option value="events">events</option>
          </select>
          <div className="button-row">
            <button className="primary-button" onClick={createJob}>创建任务</button>
            <button className="ghost-button" onClick={processJob} disabled={!job?.id}>处理当前任务</button>
          </div>
          {job && <JsonBlock value={job} compact />}
        </section>
      </div>
    </AdminPageShell>
  );
}

function AdminPageShell({
  eyebrow,
  title,
  description,
  children,
  state = "done",
  error = "",
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  state?: LoadState;
  error?: string;
  action?: ReactNode;
}) {
  return (
    <section className="admin-page">
      <header className="admin-page-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <span>{description}</span>
        </div>
        {action}
      </header>
      {state === "loading" && <div className="admin-loading"><Loader2 className="spin" size={19} /> 正在读取数据...</div>}
      {state === "error" && <div className="error-banner">{error || "请求失败"}</div>}
      {state !== "loading" && state !== "error" && children}
    </section>
  );
}

function PanelTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return <div className="panel-title">{icon}<h2>{title}</h2></div>;
}

function MetricCard({ title, value, tone = "" }: { title: string; value: string | number; tone?: string }) {
  return <article className={`metric-card ${tone}`}><span>{title}</span><strong>{value}</strong></article>;
}

function StatusPill({ value }: { value: string }) {
  return <span className={`status-pill ${value}`}>{value}</span>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

function JsonBlock({ value, compact = false }: { value: unknown; compact?: boolean }) {
  return <pre className={`json-block ${compact ? "compact" : ""}`}>{JSON.stringify(value, null, 2)}</pre>;
}

function QualityIssue({ issue }: { issue: Record<string, unknown> }) {
  const target = String(issue.event_id || issue.target_id || "");
  const link = issue.target_type === "relation" ? "/admin/relations" : `/admin/events/${target}`;
  return (
    <Link className="issue-card" to={link}>
      <span>{String(issue.issue_type)} / {String(issue.severity)}</span>
      <strong>{String(issue.title || issue.target_id)}</strong>
      <p>{String(issue.description || "")}</p>
    </Link>
  );
}

function splitList(value: string) {
  return value
    .split(/[;；、\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function sourceFormToPayload(form: SourceFormState) {
  return {
    source_title: form.source_title,
    source_type: form.source_type,
    url: form.url,
    citation: form.citation,
    excerpt: form.excerpt,
    reliability: Number(form.reliability || 0),
    is_primary: form.is_primary,
  };
}

function relationFormToPayload(form: RelationFormState) {
  return {
    source_event_id: form.source_event_id,
    target_event_id: form.target_event_id,
    relation_type: form.relation_type,
    explanation: form.explanation,
    confidence: Number(form.confidence || 0),
  };
}

function metric(record: Record<string, number> | undefined, key: string) {
  return record?.[key] ?? 0;
}

function percentFrom(record: Record<string, unknown>, key: string) {
  const value = record[key];
  if (typeof value === "number") return `${Math.round(value * 100)}%`;
  return "-";
}

function readError(err: unknown) {
  return err instanceof Error ? err.message : "请求失败";
}
