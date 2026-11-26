import { lazy, useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/authStore";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Login } from "./pages/Login";
import { Finances } from "./pages/Finances";

const Today = lazy(() =>
  import("./pages/Today").then((module) => ({ default: module.Today })),
);
const Inbox = lazy(() =>
  import("./pages/Inbox").then((module) => ({ default: module.Inbox })),
);
const Projects = lazy(() =>
  import("./pages/Projects").then((module) => ({ default: module.Projects })),
);
const ProjectDetail = lazy(() =>
  import("./pages/ProjectDetail").then((module) => ({
    default: module.ProjectDetail,
  })),
);
const Calendar = lazy(() =>
  import("./pages/Calendar").then((module) => ({ default: module.Calendar })),
);
const FinanceAccounts = lazy(() =>
  import("./pages/FinanceAccounts").then((module) => ({
    default: module.FinanceAccounts,
  })),
);
const FinanceTransactions = lazy(() =>
  import("./pages/FinanceTransactions").then((module) => ({
    default: module.FinanceTransactions,
  })),
);
const FinancePeople = lazy(() =>
  import("./pages/FinancePeople").then((module) => ({
    default: module.FinancePeople,
  })),
);
const FinancePersonDetails = lazy(() =>
  import("./pages/FinancePersonDetails").then((module) => ({
    default: module.FinancePersonDetails,
  })),
);
const FinanceCashflow = lazy(() =>
  import("./pages/FinanceCashflow").then((module) => ({
    default: module.FinanceCashflow,
  })),
);
const FinanceBudgets = lazy(() =>
  import("./pages/FinanceBudgets").then((module) => ({
    default: module.FinanceBudgets,
  })),
);
const FinanceReports = lazy(() =>
  import("./pages/FinanceReports").then((module) => ({
    default: module.FinanceReports,
  })),
);
const Advisor = lazy(() =>
  import("./pages/Advisor").then((module) => ({ default: module.Advisor })),
);
const Documents = lazy(() =>
  import("./pages/Documents").then((module) => ({ default: module.Documents })),
);
const Settings = lazy(() =>
  import("./pages/Settings").then((module) => ({ default: module.Settings })),
);
const AISettings = lazy(() =>
  import("./pages/AISettings").then((module) => ({
    default: module.AISettings,
  })),
);
const FinanceSettings = lazy(() =>
  import("./pages/FinanceSettings").then((module) => ({
    default: module.FinanceSettings,
  })),
);
const FinanceCategorizationSettings = lazy(() =>
  import("./pages/FinanceCategorizationSettings").then((module) => ({
    default: module.FinanceCategorizationSettings,
  })),
);
const FinanceLoans = lazy(() =>
  import("./pages/FinanceLoans").then((module) => ({
    default: module.FinanceLoans,
  })),
);
const FinanceCreditCards = lazy(() =>
  import("./pages/FinanceCreditCards").then((module) => ({
    default: module.FinanceCreditCards,
  })),
);
const FinanceCreditCardDetails = lazy(() =>
  import("./pages/FinanceCreditCardDetails").then((module) => ({
    default: module.FinanceCreditCardDetails,
  })),
);
const FinanceDocuments = lazy(() =>
  import("./pages/FinanceDocuments").then((module) => ({
    default: module.FinanceDocuments,
  })),
);
const FinanceImports = lazy(() =>
  import("./pages/FinanceImports").then((module) => ({
    default: module.FinanceImports,
  })),
);
const FinanceImportReview = lazy(() =>
  import("./pages/FinanceImportReview").then((module) => ({
    default: module.FinanceImportReview,
  })),
);
const FinanceCategoryProposals = lazy(() =>
  import("./pages/FinanceCategoryProposals").then((module) => ({
    default: module.FinanceCategoryProposals,
  })),
);

export default function App() {
  const fetchUser = useAuthStore((s) => s.fetchUser);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/today" replace />} />
        <Route path="/today" element={<Today />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/finances" element={<Finances />} />
        <Route
          path="/finances/accounts"
          element={<Navigate to="/settings/finances/accounts" replace />}
        />
        <Route
          path="/finances/transactions"
          element={<FinanceTransactions />}
        />
        <Route
          path="/finances/cashflow"
          element={<FinanceCashflow configure={false} />}
        />
        <Route
          path="/finances/budgets"
          element={<FinanceBudgets configure={false} />}
        />
        <Route path="/finances/reports" element={<FinanceReports />} />
        <Route path="/finances/loans" element={<FinanceLoans />} />
        <Route path="/finances/people" element={<FinancePeople />} />
        <Route
          path="/finances/people/:personId"
          element={<FinancePersonDetails />}
        />
        <Route path="/finances/documents" element={<FinanceDocuments />} />
        <Route path="/finances/imports" element={<FinanceImports />} />
        <Route
          path="/finances/imports/:batchId"
          element={<FinanceImportReview />}
        />
        <Route
          path="/finances/proposals"
          element={<FinanceCategoryProposals />}
        />
        <Route path="/advisor" element={<Advisor />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/ai" element={<AISettings />} />
        <Route path="/settings/finances" element={<FinanceSettings />}>
          <Route index element={<Navigate to="accounts" replace />} />
          <Route
            path="accounts"
            element={<FinanceAccounts section="accounts" />}
          />
          <Route
            path="categories"
            element={<FinanceAccounts section="categories" />}
          />
          <Route path="budgets" element={<FinanceBudgets />} />
          <Route
            path="schedules"
            element={<FinanceCashflow configure settingsSection="schedules" />}
          />
          <Route
            path="forecast"
            element={<FinanceCashflow configure settingsSection="forecast" />}
          />
          <Route path="loans" element={<FinanceLoans />} />
          <Route path="cards" element={<FinanceCreditCards />} />
          <Route
            path="cards/:accountId"
            element={<FinanceCreditCardDetails />}
          />
          <Route
            path="categorization"
            element={<FinanceCategorizationSettings />}
          />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/today" replace />} />
    </Routes>
  );
}
