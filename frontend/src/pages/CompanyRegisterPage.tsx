import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Building2, Lock, Mail, MapPin, Phone, User } from "lucide-react";
import AuthShell from "../components/AuthShell";
import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import Button from "../components/ui/Button";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import Banner from "../components/ui/Banner";
import {
  companyAddressFormFields,
  type CompanyAddressFieldKey,
} from "../lib/companyAddressFields";
import { PASSWORD_REQUIREMENTS_HINT, validatePasswordStrength } from "../utils/passwordPolicy";

function isRateLimitError(message: string): boolean {
  return /too many failed login attempts/i.test(message);
}

type AddressForm = Record<CompanyAddressFieldKey, string>;

const emptyAddress = (): AddressForm => ({
  address_line: "",
  address_line_2: "",
  district: "",
  state: "",
  pin_code: "",
  gstin: "",
});

export default function CompanyRegisterPage() {
  const { registerCompany, user, loading } = useAuth();
  const navigate = useNavigate();
  const [companyName, setCompanyName] = useState("");
  const [address, setAddress] = useState<AddressForm>(emptyAddress);
  const [companyPhone, setCompanyPhone] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [registrationAllowed, setRegistrationAllowed] = useState<boolean | null>(null);

  const setAddr = (key: CompanyAddressFieldKey, value: string) =>
    setAddress((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    if (!loading && user) {
      navigate("/dashboard", { replace: true });
    }
  }, [loading, user, navigate]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await api.get<{ allowed: boolean }>("/api/companies/registration-status", {
          skipAuthRedirect: true,
        });
        if (!cancelled) setRegistrationAllowed(status.allowed);
      } catch {
        if (!cancelled) setRegistrationAllowed(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
      await registerCompany({
        company_name: companyName.trim(),
        company_address_line: address.address_line.trim() || null,
        company_address_line_2: address.address_line_2.trim() || null,
        company_district: address.district.trim() || null,
        company_state: address.state.trim() || null,
        company_pin_code: address.pin_code.trim() || null,
        company_gstin: address.gstin.trim() || null,
        company_phone: companyPhone.trim() || null,
        owner_name: ownerName.trim() || null,
        email: email.trim(),
        password,
      });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  const closed = registrationAllowed === false;

  return (
    <AuthShell
      title="Register your company"
      subtitle="Create a new company workspace with an owner account. Your books start empty."
      footer={
        <p>
          Already have an account?{" "}
          <Link className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300" to="/login">
            Sign in
          </Link>
        </p>
      }
    >
      {closed && (
        <Banner tone="info" title="Registration closed" className="mb-4">
          Public company registration is not open right now. Contact an administrator if you need access.
        </Banner>
      )}
      {error && (
        <Banner
          tone="danger"
          title={isRateLimitError(error) ? "Registration temporarily paused" : "Registration failed"}
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
        <FormField label="Company name" required>
          {({ id }) => (
            <Input
              id={id}
              type="text"
              autoComplete="organization"
              required
              disabled={closed}
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g. Green Fields Traders"
              leftIcon={<Building2 />}
            />
          )}
        </FormField>

        <div className="space-y-3 rounded-lg border border-line/70 p-3">
          <p className="flex items-center gap-2 text-sm font-medium text-ink">
            <MapPin className="h-4 w-4 text-ink-subtle" aria-hidden="true" />
            Company address <span className="font-normal text-ink-subtle">(optional)</span>
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {companyAddressFormFields.map((f) => (
              <FormField key={f.key} label={f.label} className={f.wide ? "sm:col-span-2" : undefined}>
                {({ id }) => (
                  <Input
                    id={id}
                    type="text"
                    disabled={closed}
                    value={address[f.key]}
                    onChange={(e) => setAddr(f.key, e.target.value)}
                    placeholder={f.placeholder}
                  />
                )}
              </FormField>
            ))}
          </div>
        </div>

        <FormField label="Company phone" hint="Optional.">
          {({ id }) => (
            <Input
              id={id}
              type="tel"
              autoComplete="tel"
              disabled={closed}
              value={companyPhone}
              onChange={(e) => setCompanyPhone(e.target.value)}
              placeholder="e.g. 98765 43210"
              leftIcon={<Phone />}
            />
          )}
        </FormField>
        <FormField label="Your name" hint="Optional — owner profile name.">
          {({ id }) => (
            <Input
              id={id}
              type="text"
              autoComplete="name"
              disabled={closed}
              value={ownerName}
              onChange={(e) => setOwnerName(e.target.value)}
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
              disabled={closed}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. owner@company.com"
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
              disabled={closed}
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
              disabled={closed}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Repeat the password"
              leftIcon={<Lock />}
            />
          )}
        </FormField>
        <Button type="submit" block size="lg" loading={busy} disabled={closed || registrationAllowed === null}>
          {busy ? "Creating company…" : "Create company"}
        </Button>
      </form>
    </AuthShell>
  );
}
