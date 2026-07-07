import VoidConfirmDialog from "./VoidConfirmDialog";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: (authorizationPassword: string) => void | Promise<void>;
  dateLabel?: string;
  authError?: string;
};

export default function BackdateAuthDialog({
  open,
  onClose,
  onConfirm,
  dateLabel,
  authError,
}: Props) {
  return (
    <VoidConfirmDialog
      open={open}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Authorization required"
      description={
        dateLabel
          ? `Recording on ${dateLabel} requires your authorization password.`
          : "A past date was selected. Enter your authorization password to continue."
      }
      confirmLabel="Confirm"
      authError={authError}
    />
  );
}
