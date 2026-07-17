import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { LayoutDashboard, LineChart, Settings, ShieldCheck } from 'lucide-react';
import type { ReactNode } from 'react';

const Layout = ({ children }: { children: ReactNode }) => (
  <div className="min-h-screen bg-slate-950 text-slate-100">
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 lg:px-8">
      <header className="mb-6 flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/80 px-6 py-4 shadow-lg shadow-black/20">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.32em] text-slate-400">Scraping Engine</p>
          <h1 className="text-2xl font-semibold text-white">Realtime Analytics Dashboard</h1>
        </div>
        <nav className="flex items-center gap-2 text-sm text-slate-300">
          <a className="rounded-lg px-3 py-2 transition hover:bg-slate-800" href="/dashboard">
            <span className="mr-2 inline-flex items-center"><LayoutDashboard size={16} /></span>
            Dashboard
          </a>
          <a className="rounded-lg px-3 py-2 transition hover:bg-slate-800" href="/products">
            <span className="mr-2 inline-flex items-center"><LineChart size={16} /></span>
            Products
          </a>
          <a className="rounded-lg px-3 py-2 transition hover:bg-slate-800" href="/settings">
            <span className="mr-2 inline-flex items-center"><Settings size={16} /></span>
            Settings
          </a>
        </nav>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  </div>
);

const DashboardPage = () => (
  <div className="grid gap-6 lg:grid-cols-[1.6fr_0.8fr]">
    <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.28em] text-slate-400">Overview</p>
          <h2 className="text-xl font-semibold text-white">Price tracking at a glance</h2>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-300">
          <ShieldCheck size={16} /> Live
        </div>
      </div>
      <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-6">
        <p className="text-sm leading-7 text-slate-400">
          This dashboard shell is ready for real product analytics, price history charts, and alert summaries once the backend endpoints are connected.
        </p>
      </div>
    </section>

    <aside className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
      <h3 className="mb-4 text-lg font-semibold text-white">System status</h3>
      <div className="space-y-3">
        {[
          ['Authentication', 'JWT-enabled'],
          ['Scraping jobs', 'Celery queue'],
          ['Real-time alerts', 'WebSocket ready'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
            <p className="text-sm text-slate-400">{label}</p>
            <p className="mt-1 font-medium text-white">{value}</p>
          </div>
        ))}
      </div>
    </aside>
  </div>
);

const ProductsPage = () => (
  <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
    <h2 className="text-xl font-semibold text-white">Tracked products</h2>
    <p className="mt-3 text-sm leading-7 text-slate-400">
      Product CRUD and price history views can be connected to the backend API from here.
    </p>
  </div>
);

const SettingsPage = () => (
  <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
    <h2 className="text-xl font-semibold text-white">Preferences</h2>
    <p className="mt-3 text-sm leading-7 text-slate-400">
      Configure alert thresholds, refresh cadence, and notification destinations.
    </p>
  </div>
);

const AppShell = () => (
  <Layout>
    <Outlet />
  </Layout>
);

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'products', element: <ProductsPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);

export default function App() {
  return <Outlet />;
}
