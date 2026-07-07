import type {
  BagType,
  ProcessingBatch,
  ProcessingJob,
  ProcessingJobSummary,
  ProcessingOutputByBrand,
} from "../api/client";
import { calcPreviewTotalKg } from "./bagType";

export const PROCESSING_OUTPUT_TOLERANCE_KG = 100;

export function isActiveProcessingBatch(batch: ProcessingBatch): boolean {
  return batch.voided_at == null;
}

export function activeProcessingBatches(batches: ProcessingBatch[]): ProcessingBatch[] {
  return batches.filter(isActiveProcessingBatch);
}

export function totalOutputKg(summary: ProcessingJobSummary | ProcessingJobListSummary): number {
  if ("total_output_kg" in summary && summary.total_output_kg != null) {
    return Number(summary.total_output_kg);
  }
  return (summary.output_by_brand ?? []).reduce((sum, row) => sum + Number(row.quantity_kg), 0);
}

export function batchTotalWasteKg(batch: ProcessingBatch): number {
  return (
    Number(batch.dust_kg) +
    Number(batch.stone_kg) +
    Number(batch.sack_weight_waste_kg) +
    Number(batch.powder_kg ?? 0) +
    Number(batch.miscellaneous_waste_kg)
  );
}

export function totalPowderKgFromBatches(batches: ProcessingBatch[]): number {
  return activeProcessingBatches(batches).reduce((sum, batch) => sum + Number(batch.powder_kg ?? 0), 0);
}

export type ProcessingEntryCounts = {
  freshInputLines: number;
  outputLines: number;
  balanceReturnLines: number;
  balanceReprocessLines: number;
  netBalanceLines: number;
  batches: number;
  wasteBatches: number;
  powderBatches: number;
  lossBatches: number;
};

/** Line/batch counts behind summary metrics — shown in brackets next to each value. */
export function computeProcessingEntryCounts(batches: ProcessingBatch[]): ProcessingEntryCounts {
  const active = activeProcessingBatches(batches);
  let freshInputLines = 0;
  let outputLines = 0;
  let balanceReturnLines = 0;
  let balanceReprocessLines = 0;
  let wasteBatches = 0;
  let powderBatches = 0;

  for (const batch of active) {
    if (Number(batch.powder_kg ?? 0) > 0) {
      powderBatches += 1;
    }
    if (explicitWasteKg(batch) > 0 || Number(batch.powder_kg ?? 0) > 0) {
      wasteBatches += 1;
    }
    for (const ln of batch.input_lines) {
      if ((ln.input_source ?? "fresh") === "balance_reprocess") {
        balanceReprocessLines += 1;
      } else {
        freshInputLines += 1;
      }
    }
    outputLines += batch.output_lines.length;
    balanceReturnLines += (batch.balance_return_lines ?? []).length;
  }

  return {
    freshInputLines,
    outputLines,
    balanceReturnLines,
    balanceReprocessLines,
    netBalanceLines: balanceReturnLines + balanceReprocessLines,
    batches: active.length,
    wasteBatches,
    powderBatches,
    lossBatches: active.length,
  };
}

/** Output line count per brand — shown in brackets on snapshot output-by-brand rows. */
export function computeOutputLineCountsByBrand(batches: ProcessingBatch[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const batch of activeProcessingBatches(batches)) {
    for (const ln of batch.output_lines) {
      counts.set(ln.brand_id, (counts.get(ln.brand_id) ?? 0) + 1);
    }
  }
  return counts;
}

export function explicitWasteKg(batch: ProcessingBatch): number {
  return (
    Number(batch.dust_kg) +
    Number(batch.stone_kg) +
    Number(batch.sack_weight_waste_kg) +
    Number(batch.powder_kg ?? 0)
  );
}

function computeWasteAndMisc(
  totalFreshInput: number,
  totalBalanceReprocess: number,
  totalOutput: number,
  totalBalanceReturn: number,
  totalWaste: number
) {
  const totalMisc =
    totalFreshInput + totalBalanceReprocess - totalOutput - totalBalanceReturn - totalWaste;
  return {
    total_waste_kg: totalWaste,
    total_misc_kg: totalMisc,
    total_loss_kg: totalWaste + totalMisc,
  };
}

export function computeSummaryFromBatches(batches: ProcessingBatch[]): ProcessingJobSummary {
  const activeBatches = activeProcessingBatches(batches);
  let totalFreshInput = 0;
  let freshInputBags = 0;
  let totalBalanceReprocess = 0;
  let totalBalanceReturn = 0;
  let totalWaste = 0;
  let totalOutput = 0;
  const byBrand = new Map<number, ProcessingOutputByBrand>();

  for (const batch of activeBatches) {
    totalWaste += explicitWasteKg(batch);

    for (const ln of batch.input_lines) {
      const qty = Number(ln.quantity_kg);
      if ((ln.input_source ?? "fresh") === "balance_reprocess") {
        totalBalanceReprocess += qty;
      } else {
        totalFreshInput += qty;
        const isLoose = ln.bag_type_is_loose ?? false;
        if (!isLoose && ln.bag_count > 0) {
          freshInputBags += ln.bag_count;
        }
      }
    }

    for (const ln of batch.balance_return_lines ?? []) {
      totalBalanceReturn += Number(ln.quantity_kg);
    }

    for (const ln of batch.output_lines) {
      totalOutput += Number(ln.quantity_kg);
      const existing = byBrand.get(ln.brand_id);
      if (existing) {
        existing.quantity_kg = String(Number(existing.quantity_kg) + Number(ln.quantity_kg));
        existing.bag_count += ln.bag_count;
      } else {
        byBrand.set(ln.brand_id, {
          brand_id: ln.brand_id,
          brand_name: ln.brand_name,
          quantity_kg: ln.quantity_kg,
          bag_count: ln.bag_count,
        });
      }
    }
  }

  const loss = computeWasteAndMisc(
    totalFreshInput,
    totalBalanceReprocess,
    totalOutput,
    totalBalanceReturn,
    totalWaste
  );

  return {
    total_fresh_input_kg: String(totalFreshInput),
    fresh_input_bags: freshInputBags,
    total_balance_reprocess_kg: String(totalBalanceReprocess),
    total_balance_return_kg: String(totalBalanceReturn),
    job_available_reprocess_kg: String(Math.max(totalBalanceReturn - totalBalanceReprocess, 0)),
    net_balance_kg: String(totalBalanceReturn - totalBalanceReprocess),
    output_by_brand: [...byBrand.values()].sort((a, b) =>
      (a.brand_name ?? "").localeCompare(b.brand_name ?? "")
    ),
    total_waste_kg: String(loss.total_waste_kg),
    total_misc_kg: String(loss.total_misc_kg),
    total_loss_kg: String(loss.total_loss_kg),
    batch_count: activeBatches.length,
    in_process_kg: "0",
  };
}

export function jobAvailableReprocessKg(summary: ProcessingJobSummary): number {
  if (summary.job_available_reprocess_kg != null) {
    return Math.max(Number(summary.job_available_reprocess_kg), 0);
  }
  return Math.max(
    Number(summary.total_balance_return_kg) - Number(summary.total_balance_reprocess_kg),
    0
  );
}

export function jobSummary(job: ProcessingJob): ProcessingJobSummary {
  if (job.summary) return job.summary;
  return computeSummaryFromBatches(job.batches ?? []);
}

export type PendingMassBalanceBatch = {
  freshInputLines?: Array<{
    input_source?: string;
    bag_type_id: number | string;
    bag_count: number;
    loose_kg: number;
  }>;
  outputLines?: Array<{
    bag_type_id: number | string;
    bag_count: number;
    loose_kg: number;
  }>;
  balanceReturnLines?: Array<{
    bag_type_id: number | string;
    bag_count: number;
    loose_kg: number;
  }>;
  dustKg?: number;
  stoneKg?: number;
  sackWeightWasteKg?: number;
  powderKg?: number;
  miscellaneousWasteKg?: number;
};

export type MassBalanceState = {
  freshInputKg: number;
  totalOutflowKg: number;
  allowanceRemainingKg: number;
  isValid: boolean;
  errorMessage: string | null;
};

function lineQuantityKg(
  bagTypes: BagType[],
  line: { bag_type_id: number | string; bag_count: number; loose_kg: number }
): number {
  const bt = bagTypes.find((b) => String(b.id) === String(line.bag_type_id));
  return calcPreviewTotalKg(bt, line.bag_count, line.loose_kg);
}

export function computeMassBalance(
  batches: ProcessingBatch[],
  bagTypes: BagType[],
  pending?: PendingMassBalanceBatch
): MassBalanceState {
  let freshInputKg = 0;
  let totalOutflowKg = 0;
  let outputBalanceKg = 0;
  const activeBatches = activeProcessingBatches(batches);

  for (const batch of activeBatches) {
    totalOutflowKg += batchTotalWasteKg(batch);
    for (const ln of batch.input_lines) {
      if ((ln.input_source ?? "fresh") !== "balance_reprocess") {
        freshInputKg += Number(ln.quantity_kg);
      }
    }
    for (const ln of batch.output_lines) {
      const qty = Number(ln.quantity_kg);
      totalOutflowKg += qty;
      outputBalanceKg += qty;
    }
    for (const ln of batch.balance_return_lines ?? []) {
      const qty = Number(ln.quantity_kg);
      totalOutflowKg += qty;
      outputBalanceKg += qty;
    }
  }

  for (const ln of pending?.freshInputLines ?? []) {
    if ((ln.input_source ?? "fresh") !== "balance_reprocess") {
      freshInputKg += lineQuantityKg(bagTypes, ln);
    }
  }

  for (const ln of pending?.outputLines ?? []) {
    const qty = lineQuantityKg(bagTypes, ln);
    totalOutflowKg += qty;
    outputBalanceKg += qty;
  }

  for (const ln of pending?.balanceReturnLines ?? []) {
    const qty = lineQuantityKg(bagTypes, ln);
    totalOutflowKg += qty;
    outputBalanceKg += qty;
  }

  totalOutflowKg += pending?.dustKg ?? 0;
  totalOutflowKg += pending?.stoneKg ?? 0;
  totalOutflowKg += pending?.sackWeightWasteKg ?? 0;
  totalOutflowKg += pending?.powderKg ?? 0;
  totalOutflowKg += pending?.miscellaneousWasteKg ?? 0;

  const allowanceRemainingKg =
    freshInputKg + PROCESSING_OUTPUT_TOLERANCE_KG - totalOutflowKg;

  let errorMessage: string | null = null;
  if (outputBalanceKg > 0 && freshInputKg === 0) {
    errorMessage =
      "Record fresh input from stock before submitting output or balance return.";
  } else if (totalOutflowKg > freshInputKg + PROCESSING_OUTPUT_TOLERANCE_KG) {
    errorMessage = `Total outflow (${totalOutflowKg.toFixed(2)} kg) exceeds fresh input (${freshInputKg.toFixed(2)} kg) plus the ${PROCESSING_OUTPUT_TOLERANCE_KG} kg allowance.`;
  }

  return {
    freshInputKg,
    totalOutflowKg,
    allowanceRemainingKg,
    isValid: errorMessage === null,
    errorMessage,
  };
}
