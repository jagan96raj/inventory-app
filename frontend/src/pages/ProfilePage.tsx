import { FormEvent, useEffect, useState } from "react";
import { Building2, Save, User as UserIcon } from "lucide-react";
import { companiesApi, type Company } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS } from "../lib/permissions";
import {
  companyAddressFormFields,
  formatCompanyAddressLines,
  type CompanyAddressFieldKey,
} from "../lib/companyAddressFields";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Banner from "../components/ui/Banner";
import { Card, CardBody, CardFooter, CardHeader } from "../components/ui/Card";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import { toast } from "../components/ui/Toaster";

type AddressForm = Record<CompanyAddressFieldKey, string>;

const emptyAddress = (): AddressForm => ({
  address_line: "",
  address_line_2: "",
  district: "",
  state: "",
  pin_code: "",
  gstin: "",
});

function addressFromCompany(c: Company): AddressForm {
  return {
    address_line: c.address_line ?? "",
    address_line_2: c.address_line_2 ?? "",
    district: c.district ?? "",
    state: c.state ?? "",
    pin_code: c.pin_code ?? "",
    gstin: c.gstin ?? "",
  };
}

export default function ProfilePage() {
  const { user, refreshMe } = useAuth();
  const isOwner = user?.role === "owner";

  const [company, setCompany] = useState<Company | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState<AddressForm>(emptyAddress);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const setAddr = (key: CompanyAddressFieldKey, value: string) =>
    setAddress((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const c = await companiesApi.getMe();
        if (cancelled) return;
        setCompany(c);
        setName(c.name ?? "");
        setPhone(c.phone ?? "");
        setAddress(addressFromCompany(c));
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load company");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!isOwner) {
      setError("Only the owner can edit company details.");
      return;
    }
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Company name is required");
      return;
    }
    if (trimmed.length > 255) {
      setError("Company name must be at most 255 characters");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = await companiesApi.updateMe({
        name: trimmed,
        address_line: address.address_line.trim() || null,
        address_line_2: address.address_line_2.trim() || null,
        district: address.district.trim() || null,
        state: address.state.trim() || null,
        pin_code: address.pin_code.trim() || null,
        gstin: address.gstin.trim() || null,
        phone: phone.trim() || null,
      });
      setCompany(next);
      setName(next.name ?? "");
      setPhone(next.phone ?? "");
      setAddress(addressFromCompany(next));
      try {
        await refreshMe();
      } catch {
        /* company already saved — ignore session refresh glitches */
      }
      toast.success("Company details saved");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not save";
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const roleLabel = user?.role ? ROLE_LABELS[user.role] : "Unassigned";
  const readOnlyAddressLines = company ? formatCompanyAddressLines(company) : [];

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Profile"
        subtitle="Your account details and company information used on printed bills."
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="space-y-5">
        <Card className="max-w-2xl">
          <CardHeader title="Account" subtitle="Signed-in person (view only)." />
          <CardBody className="space-y-3 text-sm">
            <div className="flex items-start gap-3">
              <UserIcon className="mt-0.5 h-4 w-4 shrink-0 text-ink-subtle" aria-hidden="true" />
              <div className="min-w-0 space-y-1">
                <p>
                  <span className="text-ink-muted">Name: </span>
                  <span className="font-semibold text-ink">{user?.name?.trim() || "—"}</span>
                </p>
                <p>
                  <span className="text-ink-muted">Email: </span>
                  <span className="font-semibold text-ink">{user?.email || "—"}</span>
                </p>
                <p>
                  <span className="text-ink-muted">Role: </span>
                  <span className="font-semibold text-ink">{roleLabel}</span>
                </p>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="max-w-2xl">
          <CardHeader
            title="Company"
            subtitle={
              isOwner
                ? "Shown on printed bills. Edit and save to update."
                : "Shown on printed bills. Only the owner can edit company details."
            }
            actions={
              isOwner && !loading ? (
                <Button
                  type="submit"
                  form="company-profile-form"
                  loading={busy}
                  disabled={busy}
                  leftIcon={<Save className="h-4 w-4" />}
                >
                  Save company
                </Button>
              ) : undefined
            }
          />
          {loading ? (
            <CardBody>
              <p className="text-sm text-ink-muted">Loading company…</p>
            </CardBody>
          ) : isOwner ? (
            <form id="company-profile-form" onSubmit={(e) => void submit(e)} noValidate>
              <CardBody className="space-y-4">
                <FormField label="Company name" required>
                  {({ id }) => (
                    <Input
                      id={id}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your business name"
                      leftIcon={<Building2 />}
                      maxLength={255}
                      required
                    />
                  )}
                </FormField>
                <FormField label="Phone">
                  {({ id }) => (
                    <Input
                      id={id}
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="Contact number"
                      maxLength={50}
                    />
                  )}
                </FormField>
                <div className="grid gap-4 sm:grid-cols-2">
                  {companyAddressFormFields.map((f) => (
                    <FormField key={f.key} label={f.label} className={f.wide ? "sm:col-span-2" : undefined}>
                      {({ id }) => (
                        <Input
                          id={id}
                          value={address[f.key]}
                          onChange={(e) => setAddr(f.key, e.target.value)}
                          placeholder={f.placeholder}
                          maxLength={f.key === "gstin" ? 20 : f.key === "pin_code" ? 12 : 500}
                        />
                      )}
                    </FormField>
                  ))}
                </div>
              </CardBody>
              <CardFooter>
                <Button type="submit" loading={busy} disabled={busy} leftIcon={<Save className="h-4 w-4" />}>
                  Save company
                </Button>
              </CardFooter>
            </form>
          ) : (
            <CardBody className="space-y-3 text-sm">
              <p>
                <span className="text-ink-muted">Name: </span>
                <span className="font-semibold text-ink">{company?.name || "—"}</span>
              </p>
              <p>
                <span className="text-ink-muted">Phone: </span>
                <span className="font-semibold text-ink">{company?.phone?.trim() || "—"}</span>
              </p>
              <div>
                <span className="text-ink-muted">Address: </span>
                {readOnlyAddressLines.length ? (
                  <div className="mt-1 font-semibold text-ink">
                    {readOnlyAddressLines.map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                  </div>
                ) : (
                  <span className="font-semibold text-ink">—</span>
                )}
              </div>
              <p>
                <span className="text-ink-muted">GSTIN: </span>
                <span className="font-semibold text-ink">{company?.gstin?.trim() || "—"}</span>
              </p>
              <p className="rounded-lg border border-line/60 bg-surface-muted/40 p-3 text-xs text-ink-muted">
                Only the owner can edit company details.
              </p>
            </CardBody>
          )}
        </Card>
      </div>
    </>
  );
}
