const FAILURE_LABELS: Record<string, string> = {
  invalid_credentials: "Invalid credentials",
  rate_limited: "Rate limited",
  not_allowed: "Not allowed",
  invalid_otp: "Invalid OTP",
};

export function loginFailureReasonLabel(reason: string | null | undefined): string {
  if (!reason) return "—";
  return FAILURE_LABELS[reason] ?? reason.replace(/_/g, " ");
}
