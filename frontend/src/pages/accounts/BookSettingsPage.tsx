import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
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
import AsyncSearchCombobox from "../../components/ui/AsyncSearchCombobox";
import { toast } from "../../components/ui/Toaster";
import { useSubmitGuard } from "../../hooks/useSubmitGuard";

export default function BookSettingsPage() {
  const [settings, setSettings] = useState<BookSettings | null>(null);
  const [powderProductId, setPowderProductId] = useState<number | null>(null);
  const [powderBrandId, setPowderBrandId] = useState<number | null>(null);
  const [powderLocationId, setPowderLocationId] = useState<number | null>(null);
  const [powderBagTypeId, setPowderBagTypeId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const saveIdemRef = useRef<string | null>(null);
  const { guardedSubmit, submitDisabled } = useSubmitGuard();

  useEffect(() => {
    bookSettingsApi
      .get()
      .then((s) => {
        setSettings(s);
        setPowderProductId(s.powder_product_id ?? null);
        setPowderBrandId(s.powder_brand_id ?? null);
        setPowderLocationId(s.powder_location_id ?? null);
        setPowderBagTypeId(s.powder_bag_type_id ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load settings"));
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!saveIdemRef.current) saveIdemRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      setBusy(true);
      try {
        const next = await bookSettingsApi.update(
          {
            powder_product_id: powderProductId,
            powder_brand_id: powderBrandId,
            powder_location_id: powderLocationId,
            powder_bag_type_id: powderBagTypeId,
          },
          saveIdemRef.current!
        );
        saveIdemRef.current = null;
        setSettings(next);
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
    });
  };

  return (
    <div className="min-w-0">
      <PageHeader
        eyebrow="Accounts"
        title="Book settings"
        subtitle={
          <>
            Processing powder destination. Cash opening is set on the Cash account under Accounts. Company name, address,
            and phone for bill print are managed on{" "}
            <Link className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300" to="/profile">
              Profile
            </Link>
            .
          </>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <form onSubmit={submit} className="min-w-0 space-y-5">
        <Card className="max-w-xl min-w-0">
          <CardHeader title="Cash opening balance" subtitle="Starting cash balance used by the Accounts dashboard." />
          <CardBody className="space-y-3">
            {settings && (
              <p className="min-w-0 text-sm text-ink-muted">
                Current value:{" "}
                <span className="v2-mono font-semibold text-ink">{formatInr(settings.cash_opening_balance)}</span>
                {" · "}
                updated {formatDate(settings.cash_opening_balance_at)}
              </p>
            )}
            <p className="rounded-lg border border-line/60 bg-surface-muted/40 p-3 text-sm text-ink-muted">
              <Settings2 className="mr-1 inline h-3.5 w-3.5" />
              Set opening on the Cash account under{" "}
              <Link
                className="font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
                to="/accounts/bank-accounts"
              >
                Accounts
              </Link>
              .
            </p>
          </CardBody>
        </Card>

        <Card className="max-w-2xl min-w-0">
          <CardHeader
            title="Consolidated powder destination"
            subtitle="All processing powder posts here — not per cereal product. Inventory is split by owner (Owned vs Job work)."
          />
          <CardBody className="grid min-w-0 gap-4 sm:grid-cols-2">
            <FormField label="Powder product" hint="Generic product master (e.g. product name Powder)" className="min-w-0">
              <AsyncSearchCombobox
                value={powderProductId}
                onChange={(id) => setPowderProductId(id)}
                searchFn={searchProducts}
                placeholder="Search product…"
                emptyText="No matching product"
                initialLabel={settings?.powder_product_name ?? undefined}
              />
            </FormField>
            <FormField label="Powder brand" className="min-w-0">
              <AsyncSearchCombobox
                value={powderBrandId}
                onChange={(id) => setPowderBrandId(id)}
                searchFn={searchBrands}
                placeholder="Search brand…"
                emptyText="No matching brand"
                initialLabel={settings?.powder_brand_name ?? undefined}
              />
            </FormField>
            <FormField label="Location" className="min-w-0">
              <AsyncSearchCombobox
                value={powderLocationId}
                onChange={(id) => setPowderLocationId(id)}
                searchFn={searchLocations}
                placeholder="Search location…"
                emptyText="No matching location"
                initialLabel={settings?.powder_location_name ?? undefined}
              />
            </FormField>
            <FormField label="Bag type" hint="Loose recommended for a common powder pile" className="min-w-0">
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
          <CardFooter className="flex-col-reverse sm:flex-row">
            <Button
              type="submit"
              loading={busy}
              disabled={busy || submitDisabled}
              leftIcon={<Save className="h-4 w-4" />}
              className="min-h-11 w-full sm:w-auto"
            >
              Save
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  );
}
