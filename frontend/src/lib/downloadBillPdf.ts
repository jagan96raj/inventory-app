export async function downloadBillPdf(element: HTMLElement, billNumber: string): Promise<void> {
  const html2pdf = (await import("html2pdf.js")).default;
  const safeName = billNumber.replace(/[^\w.-]+/g, "_");
  await html2pdf()
    .set({
      margin: [12, 12, 12, 12],
      filename: `${safeName}.pdf`,
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, logging: false },
      jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      pagebreak: { mode: ["avoid-all", "css", "legacy"] },
    })
    .from(element)
    .save();
}
