'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { 
  Package, Search, Clock, CheckCircle2, Truck, XCircle, 
  ChevronRight, AlertTriangle, RefreshCw, ShoppingCart 
} from 'lucide-react';
import { Order } from '@/lib/types';

export default function OrdersDashboard() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'active' | 'delivered' | 'cancelled'>('all');
  const [search, setSearch] = useState('');

  const fetchOrders = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/orders`);
      if (!res.ok) throw new Error('Failed to fetch orders from server');
      const data = await res.json();
      setOrders(data);
    } catch (err: any) {
      setError(err.message || 'Error loading orders');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
  }, []);

  const filteredOrders = orders.filter((order) => {
    // Status filter
    if (filter === 'active' && !['Processing', 'In Transit'].includes(order.status)) return false;
    if (filter === 'delivered' && order.status !== 'Delivered') return false;
    if (filter === 'cancelled' && order.status !== 'Cancelled') return false;

    // Search filter
    if (search.trim()) {
      const query = search.toLowerCase();
      const matchId = order.id.toLowerCase().includes(query);
      const matchItem = order.items.some((item) => item.name.toLowerCase().includes(query));
      if (!matchId && !matchItem) return false;
    }
    return true;
  });

  const getStatusBadge = (status: Order['status'], delayed?: boolean) => {
    if (status === 'Delivered') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Delivered
        </span>
      );
    }
    if (status === 'In Transit') {
      return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
          delayed 
            ? 'bg-amber-50 text-amber-800 border border-amber-300' 
            : 'bg-blue-50 text-blue-700 border border-blue-200'
        }`}>
          <Truck className="w-3.5 h-3.5" />
          {delayed ? 'In Transit (Delayed)' : 'In Transit'}
        </span>
      );
    }
    if (status === 'Processing') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <Clock className="w-3.5 h-3.5" />
          Processing
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
        <XCircle className="w-3.5 h-3.5" />
        Cancelled
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Top Banner / Heading */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Your Orders</h1>
          <p className="text-sm text-slate-500 mt-1">Manage orders, track real-time delivery, or speak with our AI customer support agent.</p>
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by product or order ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition shadow-sm"
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-3 overflow-x-auto">
        {(['all', 'active', 'delivered', 'cancelled'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setFilter(tab)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold capitalize transition ${
              filter === tab
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Loading Skeletons */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="p-5 bg-white border border-slate-200 rounded-2xl animate-pulse space-y-4">
              <div className="flex justify-between items-center">
                <div className="h-4 bg-slate-200 rounded w-24"></div>
                <div className="h-6 bg-slate-200 rounded-full w-20"></div>
              </div>
              <div className="flex gap-4">
                <div className="w-20 h-20 bg-slate-200 rounded-xl"></div>
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-slate-200 rounded w-3/4"></div>
                  <div className="h-4 bg-slate-200 rounded w-1/4"></div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="p-8 text-center bg-white border border-rose-200 rounded-2xl space-y-3">
          <AlertTriangle className="w-10 h-10 text-rose-500 mx-auto" />
          <h3 className="text-lg font-bold text-slate-800">Unable to load orders</h3>
          <p className="text-sm text-slate-500">{error}</p>
          <button
            onClick={fetchOrders}
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition"
          >
            <RefreshCw className="w-4 h-4" /> Try Again
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && filteredOrders.length === 0 && (
        <div className="p-12 text-center bg-white border border-slate-200 rounded-2xl space-y-3">
          <Package className="w-12 h-12 text-slate-400 mx-auto stroke-[1.5]" />
          <h3 className="text-lg font-bold text-slate-800">No orders found</h3>
          <p className="text-sm text-slate-500 max-w-sm mx-auto">
            {search ? `No orders matching "${search}". Try searching for something else.` : 'You have no orders in this category.'}
          </p>
        </div>
      )}

      {/* Orders Grid */}
      {!loading && !error && filteredOrders.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filteredOrders.map((order) => {
            const item = order.items[0];
            return (
              <Link
                key={order.id}
                href={`/orders/${order.id}`}
                className="group block p-5 bg-white border border-slate-200 rounded-2xl hover:border-indigo-400 hover:shadow-md transition duration-200"
              >
                <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-500 uppercase tracking-wider">{order.id}</span>
                    <span className="text-slate-300">•</span>
                    <span className="text-xs text-slate-500">
                      Placed {new Date(order.placed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                  </div>
                  {getStatusBadge(order.status, order.delayed)}
                </div>

                <div className="flex gap-4 items-center">
                  <div className="relative w-20 h-20 rounded-xl overflow-hidden bg-slate-100 flex-shrink-0 border border-slate-100">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={item.image}
                      alt={item.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                    />
                  </div>

                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-bold text-slate-900 truncate group-hover:text-indigo-600 transition">
                      {item.name}
                    </h3>
                    <p className="text-xs text-slate-500 mt-1">
                      Qty: {item.quantity} • Paid via {order.payment.method}
                    </p>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-base font-extrabold text-slate-900">
                        ₹{order.payment.amount.toLocaleString('en-IN')}
                      </span>
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 group-hover:translate-x-0.5 transition">
                        View Details <ChevronRight className="w-3.5 h-3.5" />
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sub-banners for special cases */}
                {order.delayed && (
                  <div className="mt-4 px-3 py-2 bg-amber-50 rounded-xl border border-amber-200/60 flex items-center gap-2 text-xs text-amber-800">
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <span>Shipment delayed by {order.days_delayed} days. Compensation voucher available via voice support.</span>
                  </div>
                )}
                {order.already_refunded && (
                  <div className="mt-4 px-3 py-2 bg-emerald-50 rounded-xl border border-emerald-200/60 flex items-center gap-2 text-xs text-emerald-800">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                    <span>Refund of ₹{order.payment.amount.toLocaleString('en-IN')} initiated ({order.refund_id}).</span>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

