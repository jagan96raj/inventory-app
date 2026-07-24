import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import AppShell from "./components/AppShell";
import RequireAuth from "./components/RequireAuth";
import RequireRole from "./components/RequireRole";

import HomePage from "./pages/HomePage";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";

import ProductsPage from "./pages/ProductsPage";
import BrandsPage from "./pages/BrandsPage";
import LocationsPage from "./pages/LocationsPage";
import BagTypesPage from "./pages/BagTypesPage";
import CustomersPage from "./pages/CustomersPage";
import InventoryPage from "./pages/InventoryPage";
import BillsListPage from "./pages/BillsListPage";
import BillDetailPage from "./pages/BillDetailPage";
import BillPrintPage from "./pages/BillPrintPage";
import BillFormPage from "./pages/BillFormPage";
import FulfillmentPage from "./pages/FulfillmentPage";
import FulfillmentDeliverPage from "./pages/FulfillmentDeliverPage";
import FulfillmentReturnPage from "./pages/FulfillmentReturnPage";
import FulfillmentHistoryPage from "./pages/FulfillmentHistoryPage";
import AuditLogPage from "./pages/histories/AuditLogPage";
import LoginHistoryPage from "./pages/histories/LoginHistoryPage";
import BagChangePage from "./pages/BagChangePage";
import ProductTransferPage from "./pages/ProductTransferPage";
import StockDisposalPage from "./pages/StockDisposalPage";
import ProcessingListPage from "./pages/ProcessingListPage";
import ProcessingJobPage from "./pages/ProcessingJobPage";
import JobWorkListPage from "./pages/job-work/JobWorkListPage";
import JobWorkFormPage from "./pages/job-work/JobWorkFormPage";
import JobWorkDetailPage from "./pages/job-work/JobWorkDetailPage";
import JobWorkFulfillmentPage from "./pages/job-work/JobWorkFulfillmentPage";
import BagChangeHistoryPage from "./pages/operations/BagChangeHistoryPage";
import ProductTransferHistoryPage from "./pages/operations/ProductTransferHistoryPage";
import StockDisposalHistoryPage from "./pages/operations/StockDisposalHistoryPage";
import ProcessingHistoryPage from "./pages/operations/ProcessingHistoryPage";
import PaymentsPage from "./pages/PaymentsPage";
import PaymentPage from "./pages/PaymentPage";
import AccountsDashboardPage from "./pages/accounts/AccountsDashboardPage";
import CashBookListPage from "./pages/accounts/CashBookListPage";
import CashBookEntryFormPage from "./pages/accounts/CashBookEntryFormPage";
import CustomerBalancesPage from "./pages/accounts/CustomerBalancesPage";
import CustomerStatementPage from "./pages/accounts/CustomerStatementPage";
import BankAccountsMasterPage from "./pages/accounts/BankAccountsMasterPage";
import ExpenseCategoriesMasterPage from "./pages/accounts/ExpenseCategoriesMasterPage";
import BookSettingsPage from "./pages/accounts/BookSettingsPage";
import PendingAccessPage from "./pages/PendingAccessPage";
import UsersPage from "./pages/UsersPage";
import CompanyRegisterPage from "./pages/CompanyRegisterPage";
import ProfilePage from "./pages/ProfilePage";

/** Remount when landing with ?created= so a fresh list always mounts. */
function CashBookListRoute() {
  const { search } = useLocation();
  const created = new URLSearchParams(search).get("created") ?? "list";
  return <CashBookListPage key={created} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<CompanyRegisterPage />} />
      <Route path="/signup" element={<Navigate to="/register" replace />} />
      <Route element={<RequireAuth />}>
        <Route element={<RequireRole permission="bills_manage" />}>
          <Route path="/sales-bills/:id/print" element={<BillPrintPage billType="sales" />} />
          <Route path="/purchase-bills/:id/print" element={<BillPrintPage billType="purchase" />} />
        </Route>
        <Route path="/pending-access" element={<PendingAccessPage />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route element={<RequireRole permission="dashboard_view" />}>
            <Route path="/dashboard" element={<DashboardPage />} />
          </Route>
          <Route path="/home" element={<HomePage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route element={<RequireRole permission="masters_manage" />}>
            <Route path="/products" element={<ProductsPage />} />
            <Route path="/brands" element={<BrandsPage />} />
            <Route path="/locations" element={<LocationsPage />} />
            <Route path="/bag-types" element={<BagTypesPage />} />
            <Route path="/customers" element={<CustomersPage />} />
          </Route>
          <Route element={<RequireRole permission="inventory_view" />}>
            <Route path="/inventory" element={<InventoryPage />} />
          </Route>
          <Route element={<RequireRole permission="job_work_fulfillment_write" />}>
            <Route path="/job-work/fulfillment" element={<JobWorkFulfillmentPage />} />
            <Route path="/job-work/fulfillment/receive" element={<Navigate to="/job-work/fulfillment" replace />} />
            <Route path="/job-work/fulfillment/return" element={<Navigate to="/job-work/fulfillment" replace />} />
            <Route path="/job-work/return" element={<Navigate to="/job-work/fulfillment" replace />} />
          </Route>
          <Route element={<RequireRole permission="job_work_manage" />}>
            <Route path="/job-work" element={<JobWorkListPage />} />
            <Route path="/job-work/new" element={<JobWorkFormPage />} />
            <Route path="/job-work/:id" element={<JobWorkDetailPage />} />
          </Route>
          <Route element={<RequireRole permission="bills_manage" />}>
            <Route path="/sales-bills" element={<BillsListPage billType="sales" />} />
            <Route path="/sales-bills/new" element={<BillFormPage billType="sales" />} />
            <Route path="/sales-bills/:id" element={<BillDetailPage billType="sales" />} />
            <Route path="/sales-bills/:id/edit" element={<BillFormPage billType="sales" edit />} />
            <Route path="/sales-bills/:id/payment" element={<PaymentPage billType="sales" />} />
            <Route path="/purchase-bills" element={<BillsListPage billType="purchase" />} />
            <Route path="/purchase-bills/new" element={<BillFormPage billType="purchase" />} />
            <Route path="/purchase-bills/:id" element={<BillDetailPage billType="purchase" />} />
            <Route path="/purchase-bills/:id/edit" element={<BillFormPage billType="purchase" edit />} />
            <Route path="/purchase-bills/:id/payment" element={<PaymentPage billType="purchase" />} />
          </Route>
          <Route element={<RequireRole permission="payments_manage" />}>
            <Route path="/payments" element={<PaymentsPage />} />
            <Route path="/payments/new" element={<PaymentPage />} />
          </Route>
          <Route element={<RequireRole anyOf={["fulfillment_write", "fulfillment_view"]} />}>
            <Route path="/fulfillment" element={<FulfillmentPage />} />
            <Route path="/fulfillment/deliver/:lineId" element={<FulfillmentDeliverPage />} />
            <Route path="/fulfillment/return/:lineId" element={<FulfillmentReturnPage />} />
            <Route path="/histories/fulfillment" element={<FulfillmentHistoryPage />} />
            <Route path="/fulfillment/history" element={<Navigate to="/histories/fulfillment" replace />} />
          </Route>
          <Route element={<RequireRole permission="bag_change_view" />}>
            <Route path="/histories/bag-change" element={<BagChangeHistoryPage />} />
            <Route path="/operations/bag-change/history" element={<Navigate to="/histories/bag-change" replace />} />
            <Route path="/operations/bag-change" element={<BagChangePage />} />
          </Route>
          <Route element={<RequireRole permission="product_transfer_view" />}>
            <Route path="/histories/product-transfer" element={<ProductTransferHistoryPage />} />
            <Route path="/operations/product-transfer/history" element={<Navigate to="/histories/product-transfer" replace />} />
            <Route path="/operations/product-transfer" element={<ProductTransferPage />} />
          </Route>
          <Route element={<RequireRole permission="stock_disposal_view" />}>
            <Route path="/histories/stock-disposal" element={<StockDisposalHistoryPage />} />
            <Route path="/operations/stock-disposal/history" element={<Navigate to="/histories/stock-disposal" replace />} />
            <Route path="/operations/stock-disposal" element={<StockDisposalPage />} />
          </Route>
          <Route element={<RequireRole anyOf={["processing_view", "processing_manage"]} />}>
            <Route path="/histories/processing" element={<ProcessingHistoryPage />} />
            <Route path="/operations/processing/:id" element={<ProcessingJobPage />} />
            <Route path="/operations/processing" element={<ProcessingListPage />} />
            <Route path="/operations/processing/history" element={<Navigate to="/histories/processing" replace />} />
          </Route>
          <Route element={<RequireRole permission="accounts_view" />}>
            <Route path="/accounts" element={<AccountsDashboardPage />} />
            <Route path="/accounts/customers" element={<CustomerBalancesPage />} />
            <Route path="/accounts/customers/:id" element={<CustomerStatementPage />} />
          </Route>
          <Route element={<RequireRole permission="cashbook_manage" />}>
            <Route path="/accounts/cashbook" element={<CashBookListRoute />} />
            <Route path="/accounts/cashbook/new" element={<CashBookEntryFormPage />} />
            <Route path="/accounts/cashbook/:id/edit" element={<CashBookEntryFormPage />} />
          </Route>
          <Route element={<RequireRole permission="bank_accounts_manage" />}>
            <Route path="/accounts/bank-accounts" element={<BankAccountsMasterPage />} />
          </Route>
          <Route element={<RequireRole permission="expense_categories_manage" />}>
            <Route path="/accounts/expense-categories" element={<ExpenseCategoriesMasterPage />} />
          </Route>
          <Route element={<RequireRole permission="book_settings_view" />}>
            <Route path="/accounts/setup" element={<BookSettingsPage />} />
          </Route>
          <Route element={<RequireRole ownerOnly />}>
            <Route path="/histories/audit" element={<AuditLogPage />} />
            <Route path="/histories/logins" element={<LoginHistoryPage />} />
            <Route path="/users" element={<UsersPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
