import { useEffect, useRef, useState, type ReactNode } from "react";
import { Lock } from "lucide-react";
import Modal from "./Modal";
import Button from "./Button";
import FormField from "./FormField";
import Input from "./Input";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: (authorizationPassword: string) => void | Promise<void>;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  authError?: string;
};

export default function VoidConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Void",
  cancelLabel = "Cancel",
  authError,
}: Props) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setPassword("");
      setBusy(false);
      return;
    }
    const t = window.setTimeout(() => inputRef.current?.focus(), 50);
    return () => window.clearTimeout(t);
  }, [open]);

  const handleClose = () => {
    if (busy) return;
    onClose();
  };

  const handleConfirm = async () => {
    if (!password.trim()) return;
    setBusy(true);
    try {
      await onConfirm(password);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            loading={busy}
            disabled={!password.trim()}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {description ? <p className="text-base text-ink-muted">{description}</p> : null}
        <FormField
          label="Authorization password"
          hint="Enter the admin void password or your account login password."
          error={authError}
          required
        >
          {({ id, "aria-describedby": describedBy, "aria-invalid": invalid }) => (
            <Input
              ref={inputRef}
              id={id}
              type="password"
              autoComplete="current-password"
              placeholder="Required to void"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && password.trim()) void handleConfirm();
              }}
              leftIcon={<Lock className="h-4 w-4" />}
              invalid={invalid || Boolean(authError)}
              aria-describedby={describedBy}
              disabled={busy}
            />
          )}
        </FormField>
      </div>
    </Modal>
  );
}
