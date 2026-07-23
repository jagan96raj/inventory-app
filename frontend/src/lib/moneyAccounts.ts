import type { BankAccount, BankAccountKind, CashBookSourceMode } from "../api/client";

/** Map a money account to legacy payment/cash-book mode + bank id for dual-write payloads. */
export function legacyFieldsFromAccount(account: BankAccount): {
  mode: CashBookSourceMode;
  bank_account_id: number | null;
} {
  if (account.kind === "cash") {
    return { mode: "cash", bank_account_id: null };
  }
  return { mode: "bank", bank_account_id: account.id };
}

export function resolveAccountIdFromLegacy(
  accounts: BankAccount[],
  mode: CashBookSourceMode | null | undefined,
  bankAccountId: number | null | undefined
): number | "" {
  if (mode === "cash") {
    const cash = accounts.find((a) => a.kind === "cash");
    return cash ? cash.id : "";
  }
  if (mode === "bank" && bankAccountId != null) {
    return bankAccountId;
  }
  return "";
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
