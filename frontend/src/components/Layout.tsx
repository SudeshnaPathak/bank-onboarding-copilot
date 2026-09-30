import { Landmark, LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";

export function Layout({ children, subtitle }: { children: ReactNode; subtitle: string }) {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><Landmark size={20} /> <strong>Onboarding Copilot</strong><span className="muted">{subtitle}</span></div>
        <div className="who">
          <span>{user?.name} <span className="chip">{user?.role}</span></span>
          <button className="btn btn-ghost" onClick={logout}><LogOut size={14} /> Sign out</button>
        </div>
      </header>
      {children}
    </div>
  );
}
