import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { Link, useNavigate } from "react-router-dom";

import { ArrowLeft, Briefcase, Plus, Trash2 } from "lucide-react";

import {

  jobWorkApi,

  newIdempotencyKey,

} from "../../api/client";

import { useBagTypeCache } from "../../hooks/useBagTypeCache";

import { calcPreviewTotalKg, isLooseBagType } from "../../lib/bagType";

import { formatQtyKg } from "../../lib/format";

import { isAuthPasswordError, isBackdatedDate } from "../../lib/backdateAuth";

import BusinessDateField from "../../components/ui/BusinessDateField";

import BackdateAuthDialog from "../../components/ui/BackdateAuthDialog";

import {

  searchBagTypes,

  searchBrands,

  searchCustomers,

  searchProducts,

  type MasterComboOption,

} from "../../lib/masterSearch";

import {

  emptyQtyFields,

  parseBagCount,

  parseLooseKg,

  PH_BAGS,

  PH_LOOSE_KG,

} from "../../lib/qtyInput";

import PageHeader from "../../components/ui/PageHeader";

import Button from "../../components/ui/Button";

import Banner from "../../components/ui/Banner";

import FormField from "../../components/ui/FormField";

import Input from "../../components/ui/Input";

import NumberInput from "../../components/ui/NumberInput";

import Textarea from "../../components/ui/Textarea";

import AsyncSearchCombobox from "../../components/ui/AsyncSearchCombobox";

import { Card, CardBody, CardHeader } from "../../components/ui/Card";



type LineForm = {

  product_id: string;

  brand_id: string;

  bag_type_id: string;

  ordered_bags: string;

  ordered_loose_kg: string;

};



const emptyLine = (): LineForm => ({

  product_id: "",

  brand_id: "",

  bag_type_id: "",

  ...emptyQtyFields(),

});



function localIsoDate(d = new Date()): string {

  const y = d.getFullYear();

  const m = String(d.getMonth() + 1).padStart(2, "0");

  const day = String(d.getDate()).padStart(2, "0");

  return `${y}-${m}-${day}`;

}



function errMsg(e: unknown) {

  return e instanceof Error ? e.message : "Error";

}



export default function JobWorkFormPage() {

  const navigate = useNavigate();

  const bagTypeCache = useBagTypeCache();

  const [previewNumber, setPreviewNumber] = useState("");

  const [customerId, setCustomerId] = useState<number | null>(null);

  const [jobDate, setJobDate] = useState(() => localIsoDate());

  const [notes, setNotes] = useState("");

  const [lines, setLines] = useState<LineForm[]>([emptyLine()]);

  const [error, setError] = useState("");

  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);

  const [backdateAuthError, setBackdateAuthError] = useState("");

  const [saving, setSaving] = useState(false);

  const idemRef = useRef<string | null>(null);

  const maxDate = useMemo(() => localIsoDate(), []);



  useEffect(() => {

    jobWorkApi.nextNumber().then((preview) => setPreviewNumber(preview.job_number));

  }, []);



  const updateLine = (idx: number, next: LineForm) => {

    const n = [...lines];

    n[idx] = next;

    setLines(n);

  };



  const createOrder = async (authorizationPassword?: string) => {
    const complete = lines.filter((l) => l.product_id && l.brand_id && l.bag_type_id);
    if (!idemRef.current) idemRef.current = newIdempotencyKey();
    const order = await jobWorkApi.create(
      {
        customer_id: customerId!,
        job_date: jobDate,
        notes: notes.trim() || null,
        lines: complete.map((l) => {
          const bt = bagTypeCache.get(l.bag_type_id)!;
          return {
            product_id: Number(l.product_id),
            brand_id: Number(l.brand_id),
            bag_type_id: Number(l.bag_type_id),
            ordered_bags: isLooseBagType(bt) ? 0 : parseBagCount(l.ordered_bags),
            ordered_loose_kg: isLooseBagType(bt) ? parseLooseKg(l.ordered_loose_kg) : 0,
          };
        }),
      },
      idemRef.current,
      authorizationPassword
    );
    idemRef.current = null;
    navigate(`/job-work/${order.id}`);
  };

  const submit = async (e: FormEvent) => {

    e.preventDefault();

    setError("");

    if (!customerId) {

      setError("Select a customer");

      return;

    }

    if (jobDate > maxDate) {

      setError("Job date cannot be in the future");

      return;

    }

    const complete = lines.filter((l) => l.product_id && l.brand_id && l.bag_type_id);

    if (!complete.length) {

      setError("Add at least one complete line");

      return;

    }

    for (const line of complete) {

      const bt = bagTypeCache.get(line.bag_type_id);

      if (!bt) {

        setError("Invalid bag type on a line");

        return;

      }

      const qty = calcPreviewTotalKg(bt, line.ordered_bags, line.ordered_loose_kg);

      if (qty <= 0) {

        setError("Each line needs a quantity greater than zero");

        return;

      }

    }

    if (!idemRef.current) idemRef.current = newIdempotencyKey();

    if (isBackdatedDate(jobDate)) {
      setBackdateAuthError("");
      setBackdateAuthOpen(true);
      return;
    }

    setSaving(true);

    try {

      await createOrder();

    } catch (err) {

      setError(errMsg(err));

    } finally {

      setSaving(false);

    }

  };

  const confirmBackdateAuth = async (authorizationPassword: string) => {
    setBackdateAuthError("");
    setSaving(true);
    try {
      await createOrder(authorizationPassword);
      setBackdateAuthOpen(false);
    } catch (err) {
      const msg = errMsg(err);
      if (isAuthPasswordError(msg)) {
        setBackdateAuthError(msg);
      } else {
        setError(msg);
        setBackdateAuthOpen(false);
      }
      throw err;
    } finally {
      setSaving(false);
    }
  };

  return (

    <>

      <PageHeader

        eyebrow="Job work"

        title="New job work order"

        subtitle="Create order for customer material — receive against each line in fulfillment (no payment)."

        actions={

          <Link to="/job-work">

            <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>

              Back to list

            </Button>

          </Link>

        }

      />



      {error && (

        <Banner tone="danger" className="mb-4">

          {error}

        </Banner>

      )}



      <form onSubmit={submit} className="space-y-5">

        <Card>

          <CardHeader

            title="Order details"

            subtitle={previewNumber ? `Preview number: ${previewNumber}` : undefined}

          />

          <CardBody className="grid gap-4 sm:grid-cols-2">

            <FormField label="Customer" required>

              {() => (

                <AsyncSearchCombobox

                  value={customerId}

                  onChange={(id) => setCustomerId(id)}

                  searchFn={searchCustomers}

                  placeholder="Search customer…"

                  emptyText="No matching customer"

                />

              )}

            </FormField>

            <BusinessDateField label="Job date" value={jobDate} onChange={setJobDate} />

            <div className="sm:col-span-2">

              <FormField label="Notes">

                {({ id }) => (

                  <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Optional" />

                )}

              </FormField>

            </div>

          </CardBody>

        </Card>



        <Card>

          <CardHeader title="Lines" subtitle="Product, brand, bag type, and ordered quantity per line." />

          <CardBody className="space-y-4">

            {lines.map((line, idx) => {

              const bt = bagTypeCache.get(line.bag_type_id);

              const qty = calcPreviewTotalKg(bt, line.ordered_bags, line.ordered_loose_kg);

              return (

                <div key={idx} className="rounded-xl border border-line/80 bg-surface-subtle/30 p-4">

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">

                    <FormField label="Product" required>

                      {() => (

                        <AsyncSearchCombobox

                          value={line.product_id ? Number(line.product_id) : null}

                          onChange={(id) =>

                            updateLine(idx, { ...emptyLine(), product_id: id != null ? String(id) : "" })

                          }

                          searchFn={searchProducts}

                          placeholder="Search product…"

                          emptyText="No matching product"

                        />

                      )}

                    </FormField>

                    <FormField label="Brand" required>

                      {() => (

                        <AsyncSearchCombobox

                          value={line.brand_id ? Number(line.brand_id) : null}

                          onChange={(id) =>

                            updateLine(idx, {

                              ...line,

                              brand_id: id != null ? String(id) : "",

                              bag_type_id: "",

                              ...emptyQtyFields(),

                            })

                          }

                          searchFn={searchBrands}

                          placeholder="Search brand…"

                          emptyText="No matching brand"

                          disabled={!line.product_id}

                        />

                      )}

                    </FormField>

                    <FormField label="Bag type" required>

                      {() => (

                        <AsyncSearchCombobox

                          value={line.bag_type_id ? Number(line.bag_type_id) : null}

                          onChange={(id, opt) => {

                            const masterOpt = opt as MasterComboOption | undefined;

                            if (masterOpt?.bagType) bagTypeCache.remember(masterOpt.bagType);

                            updateLine(idx, {

                              ...line,

                              bag_type_id: id != null ? String(id) : "",

                              ...emptyQtyFields(),

                            });

                          }}

                          searchFn={searchBagTypes}

                          placeholder="Search bag type…"

                          emptyText="No matching bag type"

                          disabled={!line.brand_id}

                        />

                      )}

                    </FormField>

                    {bt && !isLooseBagType(bt) && (

                      <FormField label="Ordered bags" required>

                        {({ id }) => (

                          <NumberInput

                            id={id}

                            min={0}

                            step={1}

                            placeholder={PH_BAGS}

                            value={line.ordered_bags}

                            onChange={(e) => updateLine(idx, { ...line, ordered_bags: e.target.value, ordered_loose_kg: "" })}

                          />

                        )}

                      </FormField>

                    )}

                    {bt && isLooseBagType(bt) && (

                      <FormField label="Ordered kg" required>

                        {({ id }) => (

                          <NumberInput

                            id={id}

                            min={0}

                            step="0.001"

                            suffix="kg"

                            placeholder={PH_LOOSE_KG}

                            value={line.ordered_loose_kg}

                            onChange={(e) => updateLine(idx, { ...line, ordered_loose_kg: e.target.value, ordered_bags: "" })}

                          />

                        )}

                      </FormField>

                    )}

                    {qty > 0 && (

                      <FormField label="Total ordered">

                        {({ id }) => <Input id={id} readOnly value={formatQtyKg(qty)} className="v2-mono" />}

                      </FormField>

                    )}

                  </div>

                  {lines.length > 1 && (

                    <div className="mt-3 flex justify-end">

                      <Button

                        type="button"

                        variant="ghost"

                        size="sm"

                        leftIcon={<Trash2 className="h-4 w-4" />}

                        onClick={() => setLines(lines.filter((_, i) => i !== idx))}

                      >

                        Remove line

                      </Button>

                    </div>

                  )}

                </div>

              );

            })}

            <Button

              type="button"

              variant="secondary"

              size="sm"

              leftIcon={<Plus className="h-4 w-4" />}

              onClick={() => setLines([...lines, emptyLine()])}

            >

              Add line

            </Button>

          </CardBody>

        </Card>



        <div className="flex justify-end gap-2">

          <Link to="/job-work">

            <Button variant="ghost" type="button" disabled={saving}>

              Cancel

            </Button>

          </Link>

          <Button type="submit" loading={saving} leftIcon={<Briefcase className="h-4 w-4" />}>

            Create order

          </Button>

        </div>

      </form>

      <BackdateAuthDialog
        open={backdateAuthOpen}
        onClose={() => setBackdateAuthOpen(false)}
        onConfirm={confirmBackdateAuth}
        dateLabel={jobDate}
        authError={backdateAuthError || undefined}
      />

    </>

  );

}


