import { bankAccountsApi, type BankAccount, type BankAccountKind } from "../api/client";

/**
 * Load the active money accounts and pre-pick a sensible default source id.
 *
 * Used by payment pages (PaymentPage, PayBalancePage) that show a
 * "cash / bank" source picker. On network failure we silently return an
 * empty list + empty default so the picker just shows "no accounts" instead
 * of exploding the whole form.
 */
export async function loadMoneyAccountsWithDefault(): Promise<{
  accounts: BankAccount[];
  defaultId: number | "";
}> {
  try {
    const page = await bankAccountsApi.list({ limit: 200, active: "true", kind: "all" });
    return { accounts: page.items, defaultId: pickDefaultMoneyAccountId(page.items) };
  } catch {
    return { accounts: [], defaultId: "" };
  }
}

export function pickDefaultMoneyAccountId(accounts: BankAccount[]): number | "" {
  const cash = accounts.find((a) => a.kind === "cash" && a.is_active);
  if (cash) return cash.id;
  const def = accounts.find((a) => a.kind === "bank" && a.is_default && a.is_active);
  if (def) return def.id;
  const firstBank = accounts.find((a) => a.kind === "bank" && a.is_active);
  return firstBank ? firstBank.id : "";
}

export function accountsByKind(accounts: BankAccount[]): {
  cash: BankAccount[];
  bank: BankAccount[];
} {
  return {
    cash: accounts.filter((a) => a.kind === "cash"),
    bank: accounts.filter((a) => a.kind === "bank"),
  };
}

export function accountKindLabel(kind: BankAccountKind): string {
  return kind === "cash" ? "Cash" : "Bank";
}
