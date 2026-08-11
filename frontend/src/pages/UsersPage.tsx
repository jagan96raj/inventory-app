import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Clock, KeyRound, Pencil, Trash2, UserRound, UserX, UserCheck } from "lucide-react";
import { api, idempotencyHeaders, newIdempotencyKey, type AuthUser } from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { useAuth } from "../context/AuthContext";
import { PASSWORD_REQUIREMENTS_HINT, validatePasswordStrength } from "../utils/passwordPolicy";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import Banner from "../components/ui/Banner";
import Badge, { type Tone } from "../components/ui/Badge";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import Modal from "../components/ui/Modal";
import IconButton from "../components/ui/IconButton";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import { ROLE_LABELS, type UserRole } from "../lib/permissions";
import { formatDateTime } from "../lib/format";
import { cn } from "../lib/cn";

type AdminUser = AuthUser & {
  created_at?: string | null;
  last_login_at?: string | null;
  is_active?: boolean;
};

type LoginOtpResponse = {
  otp: string;
  expires_at: string;
  user_email: string;
  user_name: string | null;
};

const ROLES: UserRole[] = ["owner", "writer", "stock_manager", "factory_manager"];

function userInitials(user: AdminUser): string {
  if (user.name?.trim()) {
    const parts = user.name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return `${parts[0][0] ?? ""}${parts[parts.length - 1][0] ?? ""}`.toUpperCase();
    }
    return parts[0].slice(0, 2).toUpperCase();
  }
  return user.email.slice(0, 2).toUpperCase();
}

function roleTone(role: UserRole | null | undefined): Tone {
  switch (role) {
    case "owner":
      return "primary";
    case "writer":
      return "info";
    case "stock_manager":
      return "success";
    case "factory_manager":
      return "warning";
    default:
      return "muted";
  }
}

function avatarAccent(role: UserRole | null | undefined): string {
  switch (role) {
    case "owner":
      return "from-amber-400/25 via-orange-400/15 to-rose-400/20 text-amber-900 ring-amber-400/25 dark:text-amber-100";
    case "writer":
      return "from-sky-400/25 via-teal-400/15 to-primary-400/20 text-sky-900 ring-sky-400/25 dark:text-sky-100";
    case "stock_manager":
      return "from-emerald-400/25 via-green-400/15 to-teal-400/20 text-emerald-900 ring-emerald-400/25 dark:text-emerald-100";
    case "factory_manager":
      return "from-primary-400/25 via-primary-300/15 to-accent-400/20 text-primary-900 ring-primary-400/25 dark:text-primary-100";
    default:
      return "from-zinc-300/30 via-zinc-200/20 to-zinc-400/20 text-zinc-700 ring-zinc-300/40 dark:text-zinc-200";
  }
}

type UserRowProps = {
  user: AdminUser;
  saving: boolean;
  isSelf: boolean;
  onEdit: (user: AdminUser) => void;
  onOtp: (user: AdminUser) => void;
  onDelete: (user: AdminUser) => void;
  onToggleActive: (user: AdminUser) => void;
  onRoleChange: (userId: number, role: UserRole) => void;
};

function UserRow({ user, saving, isSelf, onEdit, onOtp, onDelete, onToggleActive, onRoleChange }: UserRowProps) {
  const displayName = user.name?.trim() || user.email;
  const roleLabel = user.role ? ROLE_LABELS[user.role] : "Unassigned";
  const isActive = user.is_active !== false;

  return (
    <li className="group relative px-4 py-4 transition-colors hover:bg-surface-subtle/70 sm:px-6 sm:py-5">
      <div className="flex min-w-0 flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-3 sm:gap-4">
          <div
            className={cn(
              "flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-sm font-semibold ring-1",
              avatarAccent(user.role)
            )}
            aria-hidden
          >
            {userInitials(user)}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="truncate text-base font-semibold text-ink">{displayName}</p>
              <Badge tone={roleTone(user.role)} size="sm">
                {roleLabel}
              </Badge>
              <Badge tone={isActive ? "success" : "danger"} size="sm">
                {isActive ? "Active" : "Disabled"}
              </Badge>
            </div>
            {user.name?.trim() && <p className="mt-0.5 truncate text-sm text-muted">{user.email}</p>}
            <p className="mt-2 inline-flex min-w-0 items-center gap-1.5 text-xs text-muted">
              <Clock className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
              <span className="min-w-0 truncate">
                {user.last_login_at ? <>Last login {formatDateTime(user.last_login_at)}</> : <>Never signed in</>}
              </span>
            </p>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-2 border-t border-line/60 pt-4 sm:flex-row sm:flex-wrap sm:items-center lg:border-t-0 lg:pt-0 lg:pl-4">
          <Select
            value={user.role ?? ""}
            disabled={saving}
            aria-label={`Role for ${user.email}`}
            className="h-11 w-full min-w-0 text-sm sm:h-10 sm:w-auto sm:min-w-[11rem]"
            onChange={(ev) => {
              const next = ev.target.value as UserRole;
              if (next) onRoleChange(user.id, next);
            }}
          >
            <option value="" disabled>
              Unassigned
            </option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </Select>
          <div className="flex flex-wrap items-center gap-1">
            <IconButton label="Edit user" size="md" variant="outline" disabled={saving} onClick={() => onEdit(user)}>
              <Pencil aria-hidden />
            </IconButton>
            <IconButton label="Generate login OTP" size="md" variant="outline" disabled={saving || !isActive} onClick={() => onOtp(user)}>
              <KeyRound aria-hidden />
            </IconButton>
            <IconButton
              label={
                isActive
                  ? isSelf
                    ? "You cannot disable your own account"
                    : "Disable user"
                  : "Enable user"
              }
              size="md"
              variant="outline"
              disabled={saving || (isActive && isSelf)}
              onClick={() => onToggleActive(user)}
              className={cn(
                isActive && !isSelf && "text-warning-700 hover:bg-warning-50 dark:hover:bg-warning-900/20"
              )}
            >
              {isActive ? <UserX aria-hidden /> : <UserCheck aria-hidden />}
            </IconButton>
            <IconButton
              label={isSelf ? "You cannot delete your own account" : "Delete user"}
              size="md"
              variant="outline"
              disabled={saving || isSelf}
              onClick={() => onDelete(user)}
              className={cn(!isSelf && "text-danger-600 hover:bg-danger-50 hover:text-danger-700 dark:hover:bg-danger-900/20")}
            >
              <Trash2 aria-hidden />
            </IconButton>
          </div>
        </div>
      </div>
    </li>
  );
}

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const createIdemRef = useRef<string | null>(null);
  const { submitting: creating, guardedSubmit: guardedCreate, submitDisabled: createDisabled } = useSubmitGuard();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("writer");

  const [editUser, setEditUser] = useState<AdminUser | null>(null);
  const [editName, setEditName] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [otpResult, setOtpResult] = useState<LoginOtpResponse | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AdminUser | null>(null);
  const [pendingDisable, setPendingDisable] = useState<AdminUser | null>(null);

  const load = useCallback(() => {
    api
      .get<AdminUser[]>("/api/users")
      .then(setUsers)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateRole = async (userId: number, nextRole: UserRole) => {
    setSaving(true);
    setError("");
    try {
      await api.patch(`/api/users/${userId}`, { role: nextRole });
      setSuccess("Role updated.");
      load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSaving(false);
    }
  };

  const openEdit = (user: AdminUser) => {
    setEditUser(user);
    setEditName(user.name ?? "");
    setEditPassword("");
    setError("");
  };

  const closeEdit = () => {
    setEditUser(null);
    setEditName("");
    setEditPassword("");
  };

  const onSaveEdit = async (e: FormEvent) => {
    e.preventDefault();
    if (!editUser) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const body: { name: string | null; password?: string } = {
        name: editName.trim() || null,
      };
      if (editPassword.trim()) {
        const policyError = validatePasswordStrength(editPassword);
        if (policyError) {
          setError(policyError);
          setSaving(false);
          return;
        }
        body.password = editPassword;
      }
      await api.patch(`/api/users/${editUser.id}`, body);
      setSuccess("User updated.");
      closeEdit();
      load();
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setSaving(false);
    }
  };

  const generateOtp = async (user: AdminUser) => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await api.post<LoginOtpResponse>(`/api/users/${user.id}/login-otp`, {});
      setOtpResult(result);
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setSaving(false);
    }
  };

  const closeOtp = () => {
    setOtpResult(null);
  };

  const removeUser = async () => {
    if (!pendingDelete) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.delete(`/api/users/${pendingDelete.id}`);
      setSuccess("User deleted.");
      setPendingDelete(null);
      load();
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async () => {
    if (!pendingDisable) return;
    const enabling = pendingDisable.is_active === false;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      await api.patch(`/api/users/${pendingDisable.id}`, { is_active: enabling });
      setSuccess(enabling ? "User enabled." : "User disabled.");
      setPendingDisable(null);
      load();
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setSaving(false);
    }
  };

  const requestToggleActive = (user: AdminUser) => {
    if (user.is_active === false) {
      void (async () => {
        setSaving(true);
        setError("");
        setSuccess("");
        try {
          await api.patch(`/api/users/${user.id}`, { is_active: true });
          setSuccess("User enabled.");
          load();
        } catch (err) {
          setError(String((err as Error).message ?? err));
        } finally {
          setSaving(false);
        }
      })();
      return;
    }
    setPendingDisable(user);
  };

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    const policyError = validatePasswordStrength(password);
    if (policyError) {
      setError(policyError);
      return;
    }
    setError("");
    setSuccess("");
    if (!createIdemRef.current) createIdemRef.current = newIdempotencyKey();
    await guardedCreate(async () => {
      try {
        await api.post(
          "/api/users",
          { email, password, name: name || null, role },
          { headers: idempotencyHeaders(createIdemRef.current!) }
        );
        createIdemRef.current = null;
        setEmail("");
        setPassword("");
        setName("");
        setRole("writer");
        setSuccess("User created.");
        load();
      } catch (err) {
        setError(String((err as Error).message ?? err));
      }
    });
  };

  const userCountLabel = users.length === 1 ? "1 account" : `${users.length} accounts`;

  return (
    <div className="min-w-0">
      <PageHeader
        eyebrow="Administration"
        title="Users"
        subtitle="Create accounts, disable access without deleting, and issue one-time login codes."
      />
      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {success && (
        <Banner tone="success" className="mb-4" onClose={() => setSuccess("")}>
          {success}
        </Banner>
      )}

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:items-start">
        <Card className="min-w-0 lg:sticky lg:top-6">
          <CardHeader title="Create user" subtitle="New users get the selected role immediately." />
          <CardBody>
            <form onSubmit={onCreate} className="space-y-4">
              <FormField label="Email">
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="min-w-0" />
              </FormField>
              <FormField label="Password" hint={PASSWORD_REQUIREMENTS_HINT}>
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required className="min-w-0" />
              </FormField>
              <FormField label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} className="min-w-0" />
              </FormField>
              <FormField label="Role">
                <Select value={role} onChange={(e) => setRole(e.target.value as UserRole)} className="min-w-0">
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABELS[r]}
                    </option>
                  ))}
                </Select>
              </FormField>
              <Button type="submit" block className="min-h-11" loading={creating} disabled={createDisabled}>
                {creating ? "Saving…" : "Create user"}
              </Button>
            </form>
          </CardBody>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <CardHeader title="All users" subtitle={userCountLabel} />
          <CardBody className="p-0">
            {users.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-4 py-12 text-center sm:px-6 sm:py-16">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500/15 to-primary-500/10 ring-1 ring-primary-500/15">
                  <UserRound className="h-7 w-7 text-primary-600 dark:text-primary-300" aria-hidden />
                </div>
                <p className="mt-4 text-base font-semibold text-ink">No users yet</p>
                <p className="mt-1 max-w-sm text-sm text-muted">
                  <span className="lg:hidden">Create the first account using the form above.</span>
                  <span className="hidden lg:inline">
                    Create the first account using the form on the left. Users will appear here with role badges and
                    quick actions.
                  </span>
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-line/70">
                {users.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    saving={saving}
                    isSelf={currentUser?.id === user.id}
                    onEdit={openEdit}
                    onOtp={(u) => void generateOtp(u)}
                    onDelete={setPendingDelete}
                    onToggleActive={requestToggleActive}
                    onRoleChange={(id, next) => void updateRole(id, next)}
                  />
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Modal
        open={!!editUser}
        onClose={closeEdit}
        title="Edit user"
        description={editUser?.email}
        size="sm"
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="secondary" onClick={closeEdit} disabled={saving} className="w-full sm:w-auto">
              Cancel
            </Button>
            <Button type="submit" form="edit-user-form" loading={saving} className="w-full sm:w-auto">
              Save changes
            </Button>
          </div>
        }
      >
        <form id="edit-user-form" onSubmit={onSaveEdit} className="space-y-4">
          <FormField label="Name">
            <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
          </FormField>
          <FormField
            label="New password"
            hint={`Leave blank to keep the current password. ${PASSWORD_REQUIREMENTS_HINT}`}
          >
            <Input
              type="password"
              value={editPassword}
              onChange={(e) => setEditPassword(e.target.value)}
              minLength={8}
              autoComplete="new-password"
              placeholder="Set a new password (optional)"
            />
          </FormField>
        </form>
      </Modal>

      <Modal
        open={!!otpResult}
        onClose={closeOtp}
        title="Login OTP"
        description="Share this code with the user. It expires in 15 minutes and works once."
        size="sm"
        footer={
          <div className="flex flex-col sm:flex-row sm:justify-end">
            <Button type="button" onClick={closeOtp} className="w-full sm:w-auto">
              Done
            </Button>
          </div>
        }
      >
        {otpResult && (
          <div className="space-y-4">
            <p className="min-w-0 break-words text-sm text-muted">
              For <span className="font-medium text-ink">{otpResult.user_email}</span>
              {otpResult.user_name ? ` (${otpResult.user_name})` : ""}
            </p>
            <div className="rounded-lg border border-line bg-surface-2 px-3 py-6 text-center sm:px-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">One-time code</p>
              <p className="mt-2 font-mono text-2xl font-semibold tracking-[0.25em] text-ink sm:text-3xl sm:tracking-[0.35em]">
                {otpResult.otp}
              </p>
            </div>
            <p className="text-sm text-muted">
              Expires {formatDateTime(otpResult.expires_at)}. The user can sign in under{" "}
              <strong>Forgot password → Login with OTP</strong> and optionally set a new password.
            </p>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={!!pendingDisable}
        onClose={() => setPendingDisable(null)}
        onConfirm={toggleActive}
        tone="warning"
        title="Disable this user?"
        description={
          pendingDisable ? (
            <>
              <strong>{pendingDisable.email}</strong> cannot log in until re-enabled. Their history and audit
              records are kept.
            </>
          ) : undefined
        }
        confirmLabel="Disable user"
      />

      <ConfirmDialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={removeUser}
        tone="danger"
        title="Delete this user?"
        description={
          pendingDelete ? (
            <>
              Permanently remove <strong>{pendingDelete.email}</strong>. They will lose access immediately and cannot sign in again.
            </>
          ) : undefined
        }
        confirmLabel="Delete user"
      />
    </div>
  );
}
