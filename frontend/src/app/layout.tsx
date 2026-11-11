import type { Metadata } from 'next';
import './globals.css';
import Link from 'next/link';
import { ShoppingBag, Sparkles } from 'lucide-react';

export const metadata: Metadata = {
  title: 'ShopSphere | Orders & Voice Support',
  description: 'AI-Powered Voice Customer Support Demo',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 flex flex-col antialiased">
        <header className="sticky top-0 z-40 bg-white border-b border-slate-200 px-6 py-4 shadow-sm">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 group">
              <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shadow-md shadow-indigo-100 group-hover:bg-indigo-700 transition">
                <ShoppingBag className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xl font-bold tracking-tight text-slate-900 group-hover:text-indigo-600 transition">
                  ShopSphere
                </span>
                <span className="hidden sm:inline-block ml-2 text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100">
                  Voice Support Demo
                </span>
              </div>
            </Link>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs font-medium text-emerald-800">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>Voice Agent Online</span>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
          {children}
        </main>

        <footer className="bg-white border-t border-slate-200 py-6 px-6 text-center text-xs text-slate-500">
          <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
            <p>© 2026 ShopSphere Inc. Built with Antigravity Agent & Gnani Vachana Voice AI.</p>
            <div className="flex items-center gap-4 text-slate-400">
              <span>Latency: &lt;1.5s</span>
              <span>•</span>
              <span>Barge-in Enabled</span>
              <span>•</span>
              <span>No Vendor Keys in Frontend</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}

