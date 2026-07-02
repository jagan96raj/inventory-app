import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Download, Printer, X } from "lucide-react";
import { api, bookSettingsApi, type Bill, type BookSettings } from "../api/client";
import BillPrintDocument from "../components/bills/BillPrintDocument";
import Button from "../components/ui/Button";
import Banner from "../components/ui/Banner";
import { downloadBillPdf } from "../lib/downloadBillPdf";

import "../styles/bill-print.css";

export default function BillPrintPage({ billType }: { billType: "sales" | "purchase" }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const printRef = useRef<HTMLDivElement>(null);
  const [bill, setBill] = useState<Bill | null>(null);
  const [bookSettings, setBookSettings] = useState<BookSettings | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pdfBusy, setPdfBusy] = useState(false);
  const autoPrinted = useRef(false);
  const autoDownloaded = useRef(false);

  const base = billType === "sales" ? "/sales-bills" : "/purchase-bills";

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      const [billData, settings] = await Promise.all([
        api.get<Bill>(`/api/bills/${id}`),
        bookSettingsApi.get().catch(() => null),
      ]);
      if (billData.bill_type !== billType) {
        setError("Bill type mismatch");
        setBill(null);
        return;
      }
      setBill(billData);
      setBookSettings(settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load bill");
      setBill(null);
    } finally {
      setLoading(false);
    }
  }, [billType, id]);

  useEffect(() => {
    void load();
  }, [load]);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  const handleDownloadPdf = useCallback(async () => {
    if (!bill || !printRef.current) return;
    setPdfBusy(true);
    try {
      await downloadBillPdf(printRef.current, bill.bill_number);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF download failed");
    } finally {
      setPdfBusy(false);
    }
  }, [bill]);

  useEffect(() => {
    if (!bill || loading) return;
    if (searchParams.get("print") === "1" && !autoPrinted.current) {
      autoPrinted.current = true;
      const timer = window.setTimeout(() => window.print(), 300);
      return () => window.clearTimeout(timer);
    }
    if (searchParams.get("download") === "1" && !autoDownloaded.current) {
      autoDownloaded.current = true;
      void handleDownloadPdf();
    }
  }, [bill, loading, searchParams, handleDownloadPdf]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-muted text-ink-muted">
        Loading bill…
      </div>
    );
  }

  if (error || !bill) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <Banner tone="danger">{error || "Bill not found"}</Banner>
        <Button className="mt-4" variant="secondary" onClick={() => navigate(base)}>
          Back to bills
        </Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-muted print:bg-white">
      <div className="no-print sticky top-0 z-10 border-b border-line bg-surface/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-ink">{bill.bill_number}</p>
            <p className="text-xs text-ink-muted">Print preview — app chrome hidden when printing</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`${base}/${bill.id}`}>
              <Button variant="ghost" size="sm" leftIcon={<X className="h-4 w-4" />}>
                Close
              </Button>
            </Link>
            <Button variant="secondary" size="sm" leftIcon={<Printer className="h-4 w-4" />} onClick={handlePrint}>
              Print
            </Button>
            <Button
              size="sm"
              leftIcon={<Download className="h-4 w-4" />}
              loading={pdfBusy}
              onClick={() => void handleDownloadPdf()}
            >
              Download PDF
            </Button>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-4xl p-4 print:p-0">
        <BillPrintDocument ref={printRef} bill={bill} bookSettings={bookSettings} billType={billType} />
      </div>
    </div>
  );
}
