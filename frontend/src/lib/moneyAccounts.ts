import type { BankAccount, BankAccountKind } from "../api/client";

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
