import { FormEvent, useEffect, useState } from "react";
import { MapPin, Phone, User, UserPlus } from "lucide-react";
import { api, type Customer } from "../api/client";
import Modal from "./ui/Modal";
import Button from "./ui/Button";
import Input from "./ui/Input";
import Textarea from "./ui/Textarea";
import FormField from "./ui/FormField";
import Banner from "./ui/Banner";
import { toast } from "./ui/Toaster";
import { addressFormFields } from "../lib/addressFormFields";

type FormState = {
  name: string;
  address_line: string;
  district: string;
  state: string;
  pin_code: string;
  phone: string;
  alternate_phone: string;
};

const emptyForm = (): FormState => ({
  name: "",
  address_line: "",
  district: "",
  state: "",
  pin_code: "",
  phone: "",
  alternate_phone: "",
});

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated: (customer: Customer) => void;
};

export default function AddCustomerDialog({ open, onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(emptyForm());
    setError("");
  }, [open]);

  const set = (key: keyof FormState, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!form.name.trim()) {
      setError("Customer name is required");
      return;
    }
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        address_line: form.address_line.trim() || null,
        district: form.district.trim() || null,
        state: form.state.trim() || null,
        pin_code: form.pin_code.trim() || null,
        phone: form.phone.trim() || null,
        alternate_phone: form.alternate_phone.trim() || null,
        credit_balance: 0,
        debit_balance: 0,
      };
      const created = await api.post<Customer>("/api/customers", body);
      toast.success(`Customer “${created.name}” added`);
      onCreated(created);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not add customer";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      headerTone="accent"
      headerIcon={<UserPlus className="h-5 w-5" strokeWidth={2.25} />}
      title="Add customer"
      description="Name and contact details only — manage opening balances from the Customers page."
      bodyClassName="bg-surface-subtle/20 dark:bg-surface-subtle/10"
      footer={
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="secondary"
            type="button"
            onClick={onClose}
            disabled={saving}
            className="w-full sm:w-auto"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form="add-customer-form"
            loading={saving}
            leftIcon={<User className="h-4 w-4" />}
            className="w-full sm:w-auto"
          >
            Add customer
          </Button>
        </div>
      }
    >
      <form id="add-customer-form" onSubmit={submit} className="space-y-6">
        {error && (
          <Banner tone="danger" onClose={() => setError("")}>
            {error}
          </Banner>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Customer name" required htmlFor="add-cust-name" className="sm:col-span-2">
            {({ id, ...aria }) => (
              <Input
                id={id}
                {...aria}
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="e.g. Suresh Traders"
                autoFocus
              />
            )}
          </FormField>
          <FormField label="Phone" htmlFor="add-cust-phone">
            {({ id, ...aria }) => (
              <Input
                id={id}
                {...aria}
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                placeholder="Primary mobile or landline"
                leftIcon={<Phone className="h-4 w-4" />}
              />
            )}
          </FormField>
          <FormField label="Alternate phone" htmlFor="add-cust-alt-phone">
            {({ id, ...aria }) => (
              <Input
                id={id}
                {...aria}
                value={form.alternate_phone}
                onChange={(e) => set("alternate_phone", e.target.value)}
                placeholder="Second contact number"
                leftIcon={<Phone className="h-4 w-4" />}
              />
            )}
          </FormField>
        </div>

        <div className="border-t border-line/70 pt-5">
          <p className="mb-4 flex items-center gap-2 text-sm font-semibold text-primary-700 dark:text-primary-300">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            Address <span className="font-normal text-ink-subtle">(optional)</span>
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {addressFormFields.map((f) => (
              <FormField
                key={f.key}
                label={f.label}
                className={f.wide ? "sm:col-span-2" : undefined}
                htmlFor={`add-cust-${f.key}`}
              >
                {({ id, ...aria }) =>
                  f.type === "textarea" ? (
                    <Textarea
                      id={id}
                      {...aria}
                      rows={2}
                      value={form[f.key as keyof FormState]}
                      onChange={(e) => set(f.key as keyof FormState, e.target.value)}
                      placeholder={f.placeholder}
                    />
                  ) : (
                    <Input
                      id={id}
                      {...aria}
                      value={form[f.key as keyof FormState]}
                      onChange={(e) => set(f.key as keyof FormState, e.target.value)}
                      placeholder={f.placeholder}
                    />
                  )
                }
              </FormField>
            ))}
          </div>
        </div>
      </form>
    </Modal>
  );
}
