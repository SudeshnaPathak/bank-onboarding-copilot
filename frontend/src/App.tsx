import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./auth/AuthContext";
import type { Role } from "./api/types";
import Apply from "./pages/Apply";
import Login from "./pages/Login";
import ReviewCase from "./pages/ReviewCase";
import ReviewQueue from "./pages/ReviewQueue";

function Guard({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="boot muted">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={user.role === "analyst" ? "/review" : "/apply"} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <div className="boot muted">Loading…</div>;
  return <Navigate to={!user ? "/login" : user.role === "analyst" ? "/review" : "/apply"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/apply" element={<Guard role="customer"><Apply /></Guard>} />
      <Route path="/review" element={<Guard role="analyst"><ReviewQueue /></Guard>} />
      <Route path="/review/:id" element={<Guard role="analyst"><ReviewCase /></Guard>} />
      <Route path="*" element={<Home />} />
    </Routes>
  );
}
