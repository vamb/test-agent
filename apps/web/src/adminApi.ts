import { API_BASE_URL } from "./api";

type QueryValue = string | number | boolean | null | undefined | Array<string | number>;
const ADMIN_API_TOKEN =
  import.meta.env.VITE_ADMIN_API_TOKEN ||
  window.localStorage.getItem("historical_admin_token") ||
  "admin";

function buildQuery(params: Record<string, QueryValue> = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((item) => search.append(key, String(item)));
      return;
    }
    search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return (await response.json()) as T;
}

export type AdminOverview = {
  events?: Record<string, number>;
  imports?: Record<string, number>;
  sources?: Record<string, number>;
  knowledge?: Record<string, number>;
  vectors?: Record<string, unknown>;
};

export type AdminDictionary = {
  regions?: string[];
  polities?: string[];
  categories?: string[];
  event_statuses?: string[];
  source_types?: string[];
  relation_types?: string[];
  time_precisions?: string[];
};

export type ImportBatch = {
  id: string;
  filename: string;
  source_note?: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  created_by?: string;
  created_at?: string;
};

export type StagingRow = {
  id: string;
  row_number: number;
  raw_payload: Record<string, unknown>;
  normalized_payload?: Record<string, unknown> | null;
  validation_errors?: string[];
  status: string;
  duplicate_candidates?: AdminEventListItem[];
  has_duplicate_candidates?: boolean;
  field_differences?: Record<string, unknown>;
};

export type AdminEventListItem = {
  id: string;
  title: string;
  start_year: number;
  end_year?: number;
  region?: string;
  polity?: string;
  status?: string;
  source_status?: string;
  confidence?: number;
  import_batch_id?: string;
  source_count?: number;
  category?: string[];
  summary?: string;
};

export type AdminSource = {
  id: string;
  event_id?: string;
  source_title: string;
  source_type: string;
  author?: string;
  publisher?: string;
  published_year?: number;
  url?: string;
  citation?: string;
  excerpt?: string;
  page_ref?: string;
  reliability?: number;
  is_primary?: boolean;
};

export type AdminRelation = {
  id: string;
  source_event_id: string;
  target_event_id: string;
  source_event_title?: string;
  target_event_title?: string;
  relation_type: string;
  explanation?: string;
  confidence?: number;
};

export type AdminEventDetail = {
  found?: boolean;
  event?: AdminEventListItem & {
    causes?: string[];
    effects?: string[];
    actors?: string[];
    start_date_text?: string;
    end_date_text?: string;
    time_precision?: string;
    modern_country?: string;
  };
  sources?: AdminSource[];
  relations?: AdminRelation[];
  changes?: Array<Record<string, unknown>>;
  import_batch?: Record<string, unknown> | null;
  embedding?: Record<string, unknown>;
};

export type DataQualityIssue = {
  issue_type: string;
  severity: string;
  target_type: string;
  target_id: string;
  title: string;
  description: string;
  event_id?: string;
};

export type KnowledgeDocument = {
  id: string;
  title: string;
  source_type?: string;
  source_uri?: string;
  citation?: string;
  status?: string;
  chunk_count?: number;
  created_at?: string;
};

export type VectorJob = {
  id: string;
  target: string;
  status: string;
  total_items?: number;
  processed_items?: number;
  failed_items?: number;
  error_message?: string;
};

export type ImportBatchReview = {
  found: boolean;
  batch?: ImportBatch;
  count?: number;
  events?: AdminEventListItem[];
  review?: {
    low_confidence_count: number;
    weak_source_count: number;
    duplicate_candidate_count: number;
    empty_structure_count: number;
    ready_for_manual_review: boolean;
  };
  issues?: Record<string, unknown[]>;
};

export const adminApi = {
  getOverview: () => request<AdminOverview>("/admin/overview"),
  getVectorStatus: () => request<Record<string, unknown>>("/vectors/status"),
  getDictionaries: () => request<AdminDictionary>("/admin/dictionaries"),
  listBatches: (params: Record<string, QueryValue> = {}) =>
    request<{ batches: ImportBatch[]; total: number }>(`/imports/batches${buildQuery(params)}`),
  parseImport: (content: string, inputFormat: "json" | "csv") =>
    request<{
      parsed: boolean;
      error?: string;
      count?: number;
      valid_rows?: number;
      error_rows?: number;
      events?: Record<string, unknown>[];
      validation_errors?: string[][];
    }>("/imports/parse", {
      method: "POST",
      body: JSON.stringify({ content, input_format: inputFormat }),
    }),
  createBatch: (payload: Record<string, unknown>) =>
    request<ImportBatch & { created: boolean; error?: string }>("/imports/batches", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getBatch: (batchId: string) =>
    request<ImportBatch & { found?: boolean }>(`/imports/batches/${batchId}`),
  getBatchReview: (batchId: string) =>
    request<ImportBatchReview>(`/admin/import-batches/${batchId}/review`),
  getStagingRows: (batchId: string) =>
    request<{ rows: StagingRow[]; count: number }>(`/imports/batches/${batchId}/staging`),
  previewBatch: (batchId: string) =>
    request<{ rows: StagingRow[]; duplicate_rows: number }>(`/imports/batches/${batchId}/preview`),
  updateStagingRow: (rowId: string, rawPayload: Record<string, unknown>) =>
    request<{ updated: boolean; error?: string; row?: StagingRow }>(`/imports/staging/${rowId}`, {
      method: "PATCH",
      body: JSON.stringify({ raw_payload: rawPayload }),
    }),
  mergeStagingRow: (rowId: string, strategy: string, targetEventId: string) =>
    request<{ merged: boolean; error?: string; row?: StagingRow }>(`/imports/staging/${rowId}/merge`, {
      method: "POST",
      body: JSON.stringify({ strategy, target_event_id: targetEventId }),
    }),
  bulkRevalidateStaging: (batchId: string) =>
    request<Record<string, unknown>>("/imports/staging/bulk-revalidate", {
      method: "POST",
      body: JSON.stringify({ batch_id: batchId }),
    }),
  confirmBatch: (batchId: string) =>
    request<Record<string, unknown>>(`/imports/batches/${batchId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirmed_by: "web-admin" }),
    }),
  rejectBatch: (batchId: string, reason: string) =>
    request<Record<string, unknown>>(`/imports/batches/${batchId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  listEvents: (params: Record<string, QueryValue> = {}) =>
    request<{ events: AdminEventListItem[]; total: number }>(`/admin/events${buildQuery(params)}`),
  getEventDetail: (eventId: string) =>
    request<AdminEventDetail>(`/admin/events/${eventId}`),
  updateEvent: (eventId: string, updates: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/admin/events/${eventId}`, {
      method: "PATCH",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, updates }),
    }),
  bulkUpdateEvents: (eventIds: string[], updates: Record<string, unknown>) =>
    request<Record<string, unknown>>("/admin/events/bulk-update", {
      method: "POST",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, event_ids: eventIds, updates }),
    }),
  addSource: (eventId: string, source: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/admin/events/${eventId}/sources`, {
      method: "POST",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, source }),
    }),
  updateSource: (sourceId: string, updates: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/admin/sources/${sourceId}`, {
      method: "PATCH",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, updates }),
    }),
  deleteSource: (sourceId: string) =>
    request<Record<string, unknown>>(`/admin/sources/${sourceId}`, {
      method: "DELETE",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true }),
    }),
  verifySource: (sourceId: string, reliability: number) =>
    request<Record<string, unknown>>(`/admin/sources/${sourceId}/verify`, {
      method: "POST",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, reliability }),
    }),
  listRelations: (params: Record<string, QueryValue> = {}) =>
    request<{ relations: AdminRelation[]; total: number }>(`/admin/relations${buildQuery(params)}`),
  createRelation: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/admin/relations", {
      method: "POST",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, ...payload }),
    }),
  updateRelation: (relationId: string, updates: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/admin/relations/${relationId}`, {
      method: "PATCH",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true, updates }),
    }),
  deleteRelation: (relationId: string) =>
    request<Record<string, unknown>>(`/admin/relations/${relationId}`, {
      method: "DELETE",
      body: JSON.stringify({ admin_token: ADMIN_API_TOKEN, confirmed: true }),
    }),
  qualitySummary: () => request<Record<string, unknown>>("/admin/data-quality/summary"),
  qualityIssues: (params: Record<string, QueryValue> = {}) =>
    request<{ issues: DataQualityIssue[]; total: number }>(`/admin/data-quality/issues${buildQuery(params)}`),
  listDocuments: (params: Record<string, QueryValue> = {}) =>
    request<{ documents: KnowledgeDocument[]; total: number }>(`/knowledge/documents${buildQuery(params)}`),
  getDocumentChunks: (documentId: string) =>
    request<{ document?: KnowledgeDocument; chunks: Array<Record<string, unknown>> }>(`/knowledge/documents/${documentId}/chunks`),
  updateDocument: (documentId: string, updates: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/knowledge/documents/${documentId}`, {
      method: "PATCH",
      body: JSON.stringify({ updates }),
    }),
  reembedDocument: (documentId: string) =>
    request<Record<string, unknown>>(`/knowledge/documents/${documentId}/reembed`, { method: "POST" }),
  createVectorJob: (target: string) =>
    request<{ job: VectorJob } | VectorJob>("/vectors/rebuild-jobs", {
      method: "POST",
      body: JSON.stringify({ target, created_by: "web-admin" }),
    }),
  processVectorJob: (jobId: string) =>
    request<Record<string, unknown>>(`/vectors/rebuild-jobs/${jobId}/process`, { method: "POST" }),
};
