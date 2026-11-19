import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <span className="brand">SimpleSight</span>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/organizations">Organizations</NavLink>
        </nav>
        <span className="spacer" />
        <span className="who">
          {user?.email} · {user?.role}
        </span>
        <button className="btn secondary" onClick={logout}>Sign out</button>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{status}</span>;
}
