export const BILL_TYPE_THEME = {
  sales: {
    row:
      "border-l-4 border-l-primary-500 bg-primary-50/95 dark:bg-primary-950/50 [&>td]:bg-primary-50/95 dark:[&>td]:bg-primary-950/50",
    billNumber: "text-primary-700 dark:text-primary-300",
    billLink: "font-semibold text-primary-700 hover:text-primary-800 hover:underline dark:text-primary-300",
    badgeTone: "primary" as const,
    tableHeader: "text-primary-800/90 dark:text-primary-200/90",
    filterGradient:
      "bg-gradient-to-br from-primary-50/55 via-surface to-primary-50/35 dark:from-primary-950/30 dark:via-surface dark:to-primary-950/20",
    filterIcon: "text-primary-600 dark:text-primary-300",
    label: "Sales",
    party: "Customer",
  },
  purchase: {
    row:
      "border-l-4 border-l-emerald-500 bg-emerald-50/95 dark:bg-emerald-950/50 [&>td]:bg-emerald-50/95 dark:[&>td]:bg-emerald-950/50",
    billNumber: "text-emerald-800 dark:text-emerald-300",
    billLink: "font-semibold text-emerald-800 hover:text-emerald-900 hover:underline dark:text-emerald-300",
    badgeTone: "success" as const,
    tableHeader: "text-emerald-800/90 dark:text-emerald-200/90",
    filterGradient:
      "bg-gradient-to-br from-emerald-50/55 via-surface to-teal-50/40 dark:from-emerald-950/30 dark:via-surface dark:to-teal-950/25",
    filterIcon: "text-emerald-600 dark:text-emerald-300",
    label: "Purchase",
    party: "Supplier",
  },
};

export function themeForBillType(billType: string) {
  return billType === "purchase" ? BILL_TYPE_THEME.purchase : BILL_TYPE_THEME.sales;
}
