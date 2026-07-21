import { api, voidAuthHeaders, type PageOut } from "../api/client";

export type MasterFieldLike = {
  key: string;
  type?: "text" | "number" | "textarea";
  optional?: boolean;
  createOnly?: boolean;
};

/** Normalize master API paths so callers may pass `/products` or `/api/products`. */
export function masterApiPath(path: string): string {
  return path.startsWith("/api") ? path : `/api${path}`;
}

export function loadMasterPage<T>(
  path: string,
  opts: { limit: number; offset: number; search?: string }
): Promise<PageOut<T>> {
  const params = new URLSearchParams({
    limit: String(opts.limit),
    offset: String(opts.offset),
  });
  if (opts.search) params.set("search", opts.search);
  return api.get<PageOut<T>>(`${masterApiPath(path)}?${params}`);
}

/** Build create/update body from form fields (shared optional-number/null rules). */
export function buildMasterFormBody(
  fields: MasterFieldLike[],
  form: Record<string, string | number>,
  opts?: { editId?: number | null }
): Record<string, unknown> {
  const editId = opts?.editId ?? null;
  const body: Record<string, unknown> = {};
  for (const f of fields) {
    if (editId && f.createOnly) continue;
    const v = form[f.key];
    if (f.optional && (v === "" || v === undefined)) {
      body[f.key] = f.type === "number" ? 0 : null;
      continue;
    }
    body[f.key] = f.type === "number" ? Number(v) : v;
  }
  return body;
}

export async function saveMasterRecord(
  path: string,
  body: Record<string, unknown>,
  editId: number | null
): Promise<void> {
  const base = masterApiPath(path);
  if (editId) await api.put(`${base}/${editId}`, body);
  else await api.post(base, body);
}

export async function deleteMasterRecord(
  path: string,
  id: number,
  authorizationPassword: string
): Promise<void> {
  await api.delete(`${masterApiPath(path)}/${id}`, {
    headers: voidAuthHeaders(authorizationPassword),
  });
}

/** Classify void-auth failures vs other delete errors for VoidConfirmDialog. */
export function isVoidAuthErrorMessage(msg: string): boolean {
  const lower = msg.toLowerCase();
  return lower.includes("authorization") || lower.includes("password");
}
