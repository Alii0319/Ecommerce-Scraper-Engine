import { BarChart3, LayoutDashboard, LogOut, ListOrdered, Settings, ShieldCheck, UserCircle2 } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

const navigationItems = [
  { label: 'Overview', to: '/dashboard', icon: LayoutDashboard },
  { label: 'Trackers', to: '/dashboard/trackers', icon: ListOrdered },
  { label: 'Analytics', to: '/dashboard/analytics', icon: BarChart3 },
  { label: 'Settings', to: '/dashboard/settings', icon: Settings },
];

export const DashboardLayout = () => {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 lg:px-8">
        <header className="mb-6 flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/80 px-6 py-4 shadow-lg shadow-black/20">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">Scraper Control Center</p>
            <h1 className="text-2xl font-semibold text-white">Realtime Tracker Operations</h1>
          </div>
          <div className="flex items-center gap-3 rounded-full border border-slate-800 bg-slate-950/80 px-3 py-2">
            <div className="rounded-full bg-emerald-500/15 p-2 text-emerald-300">
              <ShieldCheck size={16} />
            </div>
            <div className="text-sm">
              <p className="font-medium text-white">{user?.email ?? 'Signed in'}</p>
              <p className="text-slate-400">Operational mode</p>
            </div>
          </div>
        </header>

        <div className="flex flex-1 flex-col gap-6 lg:flex-row">
          <aside className="w-full rounded-3xl border border-slate-800 bg-slate-900/80 p-5 shadow-xl shadow-black/20 lg:w-72">
            <div className="mb-6 flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 p-3">
              <div className="rounded-full bg-slate-800 p-2 text-slate-300">
                <UserCircle2 size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">{user?.first_name || 'Operations'}</p>
                <p className="text-xs text-slate-400">{user?.last_name || 'Workspace'}</p>
              </div>
            </div>

            <nav className="space-y-2">
              {navigationItems.map(({ label, to, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-2xl px-3 py-3 text-sm font-medium transition ${
                      isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/70 hover:text-white'
                    }`
                  }
                >
                  <Icon size={16} />
                  {label}
                </NavLink>
              ))}
            </nav>

            <button
              type="button"
              onClick={() => {
                void logout();
              }}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-700 bg-slate-950/80 px-3 py-3 text-sm font-medium text-slate-300 transition hover:border-rose-500/40 hover:text-rose-300"
            >
              <LogOut size={16} />
              Logout
            </button>
          </aside>

          <main className="flex-1">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
};
