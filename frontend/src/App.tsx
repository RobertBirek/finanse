import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./stores/authStore";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Login } from "./pages/Login";
import { Today } from "./pages/Today";
import { Inbox } from "./pages/Inbox";
import { Projects } from "./pages/Projects";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Calendar } from "./pages/Calendar";
import { Finances } from "./pages/Finances";
import { FinanceTransactions } from "./pages/FinanceTransactions";
import { FinanceCashflow } from "./pages/FinanceCashflow";
import { FinanceBudgets } from "./pages/FinanceBudgets";
import { FinanceReports } from "./pages/FinanceReports";
import { Advisor } from "./pages/Advisor";
import { Documents } from "./pages/Documents";
import { Settings } from "./pages/Settings";

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
          path="/finances/transactions"
          element={<FinanceTransactions />}
        />
        <Route path="/finances/cashflow" element={<FinanceCashflow />} />
        <Route path="/finances/budgets" element={<FinanceBudgets />} />
        <Route path="/finances/reports" element={<FinanceReports />} />
        <Route path="/advisor" element={<Advisor />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/today" replace />} />
    </Routes>
  );
}
