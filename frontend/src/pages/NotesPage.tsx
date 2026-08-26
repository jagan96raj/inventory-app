import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  MoreHorizontal,
  NotebookPen,
  Plus,
  StickyNote,
  Users,
} from "lucide-react";
import {
  notesApi,
  type CompanyNote,
  type NoteShareRole,
} from "../api/client";
import { ROLE_LABELS, usePermissions, type UserRole } from "../lib/permissions";
import { formatDate, todayIso } from "../lib/format";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Banner from "../components/ui/Banner";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import Input from "../components/ui/Input";
import Textarea from "../components/ui/Textarea";
import FormField from "../components/ui/FormField";
import { toast } from "../components/ui/Toaster";
import { cn } from "../lib/cn";

const SHARE_ROLES: NoteShareRole[] = ["writer", "stock_manager", "factory_manager"];

const TILTS = ["-rotate-1", "rotate-1", "-rotate-[0.6deg]", "rotate-[0.8deg]", "-rotate-[1.2deg]"];

function sharedBadgeLabel(roles: string[]): string {
  if (!roles.length) return "Owner only";
  const labels = roles.map((r) => ROLE_LABELS[r as UserRole] ?? r);
  if (labels.length === 1) return `Shared with ${labels[0]}`;
  if (labels.length === 2) return `Shared with ${labels[0]} & ${labels[1]}`;
  return `Shared with ${labels.length} roles`;
}

type NoteFormState = {
  title: string;
  body: string;
  note_date: string;
};

const emptyForm = (): NoteFormState => ({
  title: "",
  body: "",
  note_date: todayIso(),
});

export default function NotesPage() {
  const { isOwner } = usePermissions();
  const [notes, setNotes] = useState<CompanyNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<CompanyNote | null>(null);
  const [form, setForm] = useState<NoteFormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CompanyNote | null>(null);
  const [visibilityNote, setVisibilityNote] = useState<CompanyNote | null>(null);
  const [visibilityRoles, setVisibilityRoles] = useState<NoteShareRole[]>([]);
  const [visibilityBusy, setVisibilityBusy] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    notesApi
      .list()
      .then(setNotes)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load notes"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openAdd = () => {
    setEditing(null);
    setForm(emptyForm());
    setFormOpen(true);
  };

  const openEdit = (note: CompanyNote) => {
    setMenuOpenId(null);
    setEditing(note);
    setForm({
      title: note.title ?? "",
      body: note.body,
      note_date: note.note_date,
    });
    setFormOpen(true);
  };

  const openVisibility = (note: CompanyNote) => {
    setMenuOpenId(null);
    setVisibilityNote(note);
    setVisibilityRoles([...(note.viewer_roles as NoteShareRole[])]);
  };

  const submitForm = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.body.trim()) {
      toast.error("Note body is required");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = {
        title: form.title.trim() || null,
        body: form.body.trim(),
        note_date: form.note_date || undefined,
      };
      if (editing) {
        await notesApi.update(editing.id, payload);
        toast.success("Note updated");
      } else {
        await notesApi.create(payload);
        toast.success("Note added");
      }
      setFormOpen(false);
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not save note";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await notesApi.remove(deleteTarget.id);
      toast.success("Note deleted");
      setDeleteTarget(null);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete");
    }
  };

  const saveVisibility = async () => {
    if (!visibilityNote) return;
    setVisibilityBusy(true);
    try {
      await notesApi.update(visibilityNote.id, { viewer_roles: visibilityRoles });
      toast.success("Visibility updated");
      setVisibilityNote(null);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not update visibility");
    } finally {
      setVisibilityBusy(false);
    }
  };

  const subtitle = useMemo(
    () =>
      isOwner
        ? "Private by default. Share individual notes with Writer, Stock, or Factory roles."
        : "Notes the owner shared with your role.",
    [isOwner]
  );

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        eyebrow="Overview"
        title="Notes"
        subtitle={subtitle}
        actions={
          isOwner ? (
            <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd} className="hidden sm:inline-flex">
              Add note
            </Button>
          ) : undefined
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {loading ? (
        <p className="text-sm text-ink-muted">Loading notes…</p>
      ) : notes.length === 0 ? (
        <EmptyState
          icon={<StickyNote />}
          title={isOwner ? "No notes yet" : "No shared notes"}
          description={
            isOwner
              ? "Pin reminders, mill tips, or follow-ups on soft paper cards."
              : "When the owner shares a note with your role, it will appear here."
          }
          action={
            isOwner ? (
              <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
                Add note
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="notes-board grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {notes.map((note, idx) => {
            const tilt = TILTS[idx % TILTS.length];
            const shared = note.viewer_roles.length > 0;
            return (
              <div
                key={note.id}
                className="notes-paper-float"
                style={{ animationDelay: `${(idx % 5) * 0.35}s` }}
              >
              <article
                className={cn(
                  "notes-paper relative flex min-h-[11rem] flex-col gap-3 p-5 shadow-md transition-shadow hover:shadow-lg",
                  tilt
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-wider text-[#6b705c]">
                      {formatDate(note.note_date)}
                    </p>
                    {note.title ? (
                      <h3 className="mt-1 truncate font-semibold text-[#3d4232]">{note.title}</h3>
                    ) : null}
                  </div>
                  {isOwner ? (
                    <div className="relative shrink-0">
                      <button
                        type="button"
                        className="rounded-lg p-1.5 text-[#6b705c] hover:bg-[#e2e4d8]/60"
                        aria-label="Note actions"
                        onClick={() => setMenuOpenId(menuOpenId === note.id ? null : note.id)}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {menuOpenId === note.id && (
                        <div className="absolute right-0 z-20 mt-1 w-44 rounded-xl border border-[#c9ccb8] bg-[#f7f6ef] py-1 text-sm shadow-lg">
                          <button
                            type="button"
                            className="block w-full px-3 py-2 text-left hover:bg-[#e8e9df]"
                            onClick={() => openEdit(note)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="block w-full px-3 py-2 text-left hover:bg-[#e8e9df]"
                            onClick={() => openVisibility(note)}
                          >
                            Who can see…
                          </button>
                          <button
                            type="button"
                            className="block w-full px-3 py-2 text-left text-rose-700 hover:bg-rose-50"
                            onClick={() => {
                              setMenuOpenId(null);
                              setDeleteTarget(note);
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-[#3d4232]">{note.body}</p>
                <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
                  <Badge tone={shared ? "primary" : "muted"} size="sm">
                    {shared ? <Users className="mr-1 inline h-3 w-3" /> : null}
                    {sharedBadgeLabel(note.viewer_roles)}
                  </Badge>
                  <span className="text-[11px] text-[#7a7f6a]">
                    {note.created_by_name || "Owner"}
                  </span>
                </div>
              </article>
              </div>
            );
          })}
        </div>
      )}

      {isOwner && (
        <button
          type="button"
          onClick={openAdd}
          className="fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden"
          aria-label="Add note"
        >
          <Plus className="h-6 w-6" />
        </button>
      )}

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? "Edit note" : "Add note"}
        description="Notes start as owner-only. Share later via Who can see…"
        headerIcon={<NotebookPen className="h-5 w-5" />}
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => setFormOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="note-form" loading={saving} disabled={saving}>
              {editing ? "Save" : "Add note"}
            </Button>
          </div>
        }
      >
        <form id="note-form" onSubmit={submitForm} className="space-y-4">
          <FormField label="Date" required>
            {({ id }) => (
              <Input
                id={id}
                type="date"
                value={form.note_date}
                onChange={(e) => setForm({ ...form, note_date: e.target.value })}
                required
              />
            )}
          </FormField>
          <FormField label="Title" hint="Optional">
            {({ id }) => (
              <Input
                id={id}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Short heading"
                maxLength={255}
              />
            )}
          </FormField>
          <FormField label="Note" required>
            {({ id }) => (
              <Textarea
                id={id}
                rows={5}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                required
                placeholder="What should the team remember?"
              />
            )}
          </FormField>
        </form>
      </Modal>

      <Modal
        open={!!visibilityNote}
        onClose={() => setVisibilityNote(null)}
        title="Who can see this note?"
        description="Owner always sees every note. Empty selection keeps it owner-only."
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={() => setVisibilityNote(null)} disabled={visibilityBusy}>
              Cancel
            </Button>
            <Button onClick={() => void saveVisibility()} loading={visibilityBusy} disabled={visibilityBusy}>
              Save
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          {SHARE_ROLES.map((role) => {
            const checked = visibilityRoles.includes(role);
            return (
              <label
                key={role}
                className="flex cursor-pointer items-center gap-3 rounded-xl border border-line px-3 py-2.5 hover:bg-surface-subtle"
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-line text-primary-600 focus:ring-primary-500"
                  checked={checked}
                  onChange={() =>
                    setVisibilityRoles((prev) =>
                      checked ? prev.filter((r) => r !== role) : [...prev, role]
                    )
                  }
                />
                <span className="text-sm font-medium text-ink">{ROLE_LABELS[role]}</span>
              </label>
            );
          })}
        </div>
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        title="Delete this note?"
        description="This cannot be undone."
        confirmLabel="Delete"
        tone="danger"
      />
    </div>
  );
}
