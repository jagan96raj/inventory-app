import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Lock, Mail, User } from "lucide-react";
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

export default function SignupPage() {
  const { signup, user, loading } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      navigate("/", { replace: true });
    }
  }, [loading, user, navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    const policyError = validatePasswordStrength(password);
    if (policyError) {
      setError(policyError);
      return;
    }

    setBusy(true);
    try {
      await signup(email.trim(), password, name.trim() || undefined);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-up failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle="Spin up a fresh workspace for your warehouse and books."
      footer={
        <p>
          Already a member?{" "}
          <Link className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300" to="/login">
            Sign in
          </Link>
        </p>
      }
    >
      {error && (
        <Banner
          tone="danger"
          title={isRateLimitError(error) ? "Sign-up temporarily paused" : "Sign-up failed"}
          className="mb-4"
        >
          {error}
          {isRateLimitError(error) && (
            <span className="mt-1 block text-sm opacity-90">
              Wait for the lockout period to end before trying again.
            </span>
          )}
        </Banner>
      )}
      <form className="space-y-4" onSubmit={(e) => void handleSubmit(e)}>
        <FormField label="Name" hint="Optional — used in your profile and emails.">
          {({ id }) => (
            <Input
              id={id}
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ravi Kumar"
              leftIcon={<User />}
            />
          )}
        </FormField>
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
        <FormField label="Password" required hint={PASSWORD_REQUIREMENTS_HINT}>
          {({ id }) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Create a strong password"
              leftIcon={<Lock />}
            />
          )}
        </FormField>
        <FormField label="Confirm password" required>
          {({ id }) => (
            <Input
              id={id}
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Repeat the password"
              leftIcon={<Lock />}
            />
          )}
        </FormField>
        <Button type="submit" block size="lg" loading={busy}>
          {busy ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
