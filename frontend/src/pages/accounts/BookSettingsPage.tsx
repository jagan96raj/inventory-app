import { FormEvent, useEffect, useState } from "react";
import { Save, Settings2 } from "lucide-react";
import { bookSettingsApi, newIdempotencyKey, type BookSettings } from "../../api/client";
import { formatDate, formatInr } from "../../lib/format";
import {
  searchBagTypes,
  searchBrands,
  searchLocations,
  searchProducts,
} from "../../lib/masterSearch";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Banner from "../../components/ui/Banner";
import { Card, CardBody, CardFooter, CardHeader } from "../../components/ui/Card";
import FormField from "../../components/ui/FormField";
import Input from "../../components/ui/Input";
import NumberInput from "../../components/ui/NumberInput";
import AsyncSearchCombobox from "../../components/ui/AsyncSearchCombobox";
import { toast } from "../../components/ui/Toaster";

export default function BookSettingsPage() {
  const [settings, setSettings] = useState<BookSettings | null>(null);
  const [opening, setOpening] = useState("0");
  const [companyName, setCompanyName] = useState("");
  const [companyAddress, setCompanyAddress] = useState("");
  const [companyPhone, setCompanyPhone] = useState("");
  const [powderProductId, setPowderProductId] = useState<number | null>(null);
  const [powderBrandId, setPowderBrandId] = useState<number | null>(null);
  const [powderLocationId, setPowderLocationId] = useState<number | null>(null);
  const [powderBagTypeId, setPowderBagTypeId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    bookSettingsApi
      .get()
      .then((s) => {
        setSettings(s);
        setOpening(s.cash_opening_balance);
        setCompanyName(s.company_name ?? "");
        setCompanyAddress(s.company_address_line ?? "");
        setCompanyPhone(s.company_phone ?? "");
        setPowderProductId(s.powder_product_id ?? null);
        setPowderBrandId(s.powder_brand_id ?? null);
        setPowderLocationId(s.powder_location_id ?? null);
        setPowderBagTypeId(s.powder_bag_type_id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load settings"));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const next = await bookSettingsApi.update(
        {
          cash_opening_balance: opening,
          company_name: companyName.trim() || null,
          company_address_line: companyAddress.trim() || null,
          company_phone: companyPhone.trim() || null,
          powder_product_id: powderProductId,
          powder_brand_id: powderBrandId,
          powder_location_id: powderLocationId,
          powder_bag_type_id: powderBagTypeId,
        },
        newIdempotencyKey()
      );
      setSettings(next);
      setOpening(next.cash_opening_balance);
      setCompanyName(next.company_name ?? "");
      setCompanyAddress(next.company_address_line ?? "");
      setCompanyPhone(next.company_phone ?? "");
      setPowderProductId(next.powder_product_id ?? null);
      setPowderBrandId(next.powder_brand_id ?? null);
      setPowderLocationId(next.powder_location_id ?? null);
      setPowderBagTypeId(next.powder_bag_type_id ?? null);
      toast.success("Book settings saved");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not save";
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Accounts"
        title="Book settings"
        subtitle="Company header for printed bills, cash opening balance, and processing powder destination."
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <form onSubmit={submit} className="space-y-5">
        <Card className="max-w-xl">
          <CardHeader
            title="Company header (bill print)"
            subtitle="Shown at the top of printed and PDF bills. No GST or e-invoice fields."
          />
          <CardBody className="space-y-4">
            <FormField label="Company name">
              <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Your business name" />
            </FormField>
            <FormField label="Address">
              <Input
                value={companyAddress}
                onChange={(e) => setCompanyAddress(e.target.value)}
                placeholder="Street, city, state"
              />
            </FormField>
            <FormField label="Phone">
              <Input value={companyPhone} onChange={(e) => setCompanyPhone(e.target.value)} placeholder="Contact number" />
            </FormField>
          </CardBody>
        </Card>

        <Card className="max-w-xl">
          <CardHeader title="Cash opening balance" subtitle="Starting cash balance used by the Accounts dashboard." />
          <CardBody className="space-y-4">
            <FormField label="Cash opening balance (₹)">
              <NumberInput min={0} step="0.01" value={opening} onChange={(e) => setOpening(e.target.value)} />
            </FormField>
            {settings && (
              <p className="text-xs text-ink-subtle">
                Current value: <span className="v2-mono font-semibold">{formatInr(settings.cash_opening_balance)}</span> · updated{" "}
                {formatDate(settings.cash_opening_balance_at)}
              </p>
            )}
            <p className="rounded-lg border border-line/60 bg-surface-muted/40 p-3 text-xs text-ink-muted">
              <Settings2 className="mr-1 inline h-3.5 w-3.5" /> Changing this re-derives every cash balance shown across the app.
            </p>
          </CardBody>
        </Card>

        <Card className="max-w-2xl">
          <CardHeader
            title="Consolidated powder destination"
            subtitle="All processing powder posts here — not per cereal product. Inventory is split by owner (Owned vs Job work)."
          />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <FormField label="Powder product" hint="Generic product master (e.g. product name Powder)">
              <AsyncSearchCombobox
                value={powderProductId}
                onChange={(id) => setPowderProductId(id)}
                searchFn={searchProducts}
                placeholder="Search product…"
                emptyText="No matching product"
                initialLabel={settings?.powder_product_name ?? undefined}
              />
            </FormField>
            <FormField label="Powder brand">
              <AsyncSearchCombobox
                value={powderBrandId}
                onChange={(id) => setPowderBrandId(id)}
                searchFn={searchBrands}
                placeholder="Search brand…"
                emptyText="No matching brand"
                initialLabel={settings?.powder_brand_name ?? undefined}
              />
            </FormField>
            <FormField label="Location">
              <AsyncSearchCombobox
                value={powderLocationId}
                onChange={(id) => setPowderLocationId(id)}
                searchFn={searchLocations}
                placeholder="Search location…"
                emptyText="No matching location"
                initialLabel={settings?.powder_location_name ?? undefined}
              />
            </FormField>
            <FormField label="Bag type" hint="Loose recommended for a common powder pile">
              <AsyncSearchCombobox
                value={powderBagTypeId}
                onChange={(id) => setPowderBagTypeId(id)}
                searchFn={searchBagTypes}
                placeholder="Search bag type…"
                emptyText="No matching bag type"
                initialLabel={settings?.powder_bag_type_name ?? undefined}
              />
            </FormField>
          </CardBody>
          <CardFooter>
            <Button type="submit" loading={busy} leftIcon={<Save className="h-4 w-4" />}>
              Save
            </Button>
          </CardFooter>
        </Card>
      </form>
    </>
  );
}
