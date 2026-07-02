import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { KeyRound, Lock, Mail } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import Banner from "../components/ui/Banner";
import { PASSWORD_REQUIREMENTS_HINT, validatePasswordStrength } from "../utils/passwordPolicy";

function isRateLimitError(message: string): boolean {
  return /too many failed login attempts/i.test(message);
}

function isAccountDisabledError(message: string): boolean {
  return /account.*disabled|disabled.*contact the owner/i.test(message);
}

type LoginMode = "password" | "otp";

export default function LoginPage() {
  const { login, loginWithOtp, user, loading } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<LoginMode>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const nextPath = searchParams.get("next") || "/";

  useEffect(() => {
    if (!loading && user) {
      navigate(nextPath.startsWith("/") ? nextPath : "/", { replace: true });
    }
  }, [loading, user, navigate, nextPath]);

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(nextPath.startsWith("/") ? nextPath : "/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  const handleOtpSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (newPassword.trim()) {
      const policyError = validatePasswordStrength(newPassword.trim());
      if (policyError) {
        setError(policyError);
        return;
      }
    }
    setBusy(true);
    try {
      await loginWithOtp(email.trim(), otp.trim(), newPassword.trim() || undefined);
      navigate(nextPath.startsWith("/") ? nextPath : "/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "OTP sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title={mode === "password" ? "Welcome back" : "Login with OTP"}
      subtitle={
        mode === "password"
          ? "Sign in to manage stock, bills, and operations."
          : "Enter the 6-digit code from your owner. You can set a new password while signing in."
      }
      footer={
        <p className="text-center text-sm text-muted">
          Need access? Contact the owner to have your email added and an account created.
        </p>
      }
    >
      {error && (
        <Banner
          tone="danger"
          title={
            isRateLimitError(error)
              ? "Login temporarily paused"
              : isAccountDisabledError(error)
                ? "Account disabled"
                : "Sign-in failed"
          }
          className="mb-4"
        >
          {error}
          {isRateLimitError(error) && (
            <span className="mt-1 block text-sm opacity-90">
              Wait for the lockout period to end, or ask the owner if you need access sooner.
            </span>
          )}
          {isAccountDisabledError(error) && (
            <span className="mt-1 block text-sm opacity-90">
              Your account has been turned off. Contact the owner to have it re-enabled.
            </span>
          )}
        </Banner>
      )}

      {mode === "password" ? (
        <form className="space-y-4" onSubmit={(e) => void handlePasswordSubmit(e)}>
          <FormField label="Email" required>
            {({ id }) => (
              <Input
                id={id}
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. ravi@graintrack.in"
                leftIcon={<Mail />}
              />
            )}
          </FormField>
          <FormField label="Password" required hint="Min 8 characters.">
            {({ id }) => (
              <Input
                id={id}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                leftIcon={<Lock />}
              />
            )}
          </FormField>
          <div className="flex justify-end">
            <button
              type="button"
              className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
              onClick={() => {
                setMode("otp");
                setError("");
                setPassword("");
              }}
            >
              Forgot password?
            </button>
          </div>
          <Button type="submit" block size="lg" loading={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      ) : (
        <form className="space-y-4" onSubmit={(e) => void handleOtpSubmit(e)}>
          <Banner tone="info" className="text-sm">
            Ask the owner for a one-time login code, then sign in below. Optionally set a new password at the same time.
          </Banner>
          <FormField label="Email" required>
            {({ id }) => (
              <Input
                id={id}
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="e.g. ravi@graintrack.in"
                leftIcon={<Mail />}
              />
            )}
          </FormField>
          <FormField label="Login code" required hint="6-digit code from the owner.">
            {({ id }) => (
              <Input
                id={id}
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                leftIcon={<KeyRound />}
                maxLength={6}
              />
            )}
          </FormField>
          <FormField label="New password" hint={`Optional. ${PASSWORD_REQUIREMENTS_HINT}`}>
            {({ id }) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Set a new password"
                leftIcon={<Lock />}
                minLength={8}
              />
            )}
          </FormField>
          <div className="flex justify-end">
            <button
              type="button"
              className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
              onClick={() => {
                setMode("password");
                setError("");
                setOtp("");
                setNewPassword("");
              }}
            >
              Back to password login
            </button>
          </div>
          <Button type="submit" block size="lg" loading={busy}>
            {busy ? "Signing in…" : "Sign in with OTP"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
