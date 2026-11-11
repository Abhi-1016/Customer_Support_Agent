'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { 
  ArrowLeft, Mic, MessageSquare, CheckCircle2, Clock, 
  Truck, XCircle, MapPin, CreditCard, ShieldCheck, AlertTriangle 
} from 'lucide-react';
import { Order } from '@/lib/types';
import PreCallModal from '@/components/PreCallModal';
import VoiceSupportModal from '@/components/VoiceSupportModal';
import DemoPanel from '@/components/DemoPanel';

export default function OrderDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const orderId = params.id as string;

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [showPreCall, setShowPreCall] = useState(false);
  const [activeCallMode, setActiveCallMode] = useState<'voice' | 'text' | null>(null);

  useEffect(() => {
    const fetchOrder = async () => {
      setLoading(true);
      setError(null);
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/orders/${orderId}`);
        if (!res.ok) throw new Error('Order not found');
        const data = await res.json();
        setOrder(data);
      } catch (err: any) {
        setError(err.message || 'Error loading order');
      } finally {
        setLoading(false);
      }
    };

    if (orderId) {
      fetchOrder();
    }
  }, [orderId]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6 animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-32"></div>
        <div className="h-64 bg-white border border-slate-200 rounded-3xl"></div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="max-w-md mx-auto p-8 text-center bg-white border border-rose-200 rounded-3xl space-y-4">
        <AlertTriangle className="w-12 h-12 text-rose-500 mx-auto" />
        <h2 className="text-lg font-bold text-slate-900">Order Not Found</h2>
        <p className="text-xs text-slate-500">{error || 'Unable to locate order records.'}</p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-bold hover:bg-indigo-700 transition"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Orders
        </Link>
      </div>
    );
  }

  const item = order.items[0];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back Button */}
      <Link
        href="/"
        className="inline-flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-indigo-600 transition"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to Orders</span>
      </Link>

      {/* Main Order Card */}
      <div className="bg-white border border-slate-200 rounded-3xl p-6 sm:p-8 shadow-sm space-y-8">
        
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-100 pb-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 font-mono">{order.id}</h1>
              <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                order.status === 'Delivered' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
                order.status === 'In Transit' ? 'bg-blue-50 text-blue-700 border border-blue-200' :
                order.status === 'Processing' ? 'bg-indigo-50 text-indigo-700 border border-indigo-200' :
                'bg-slate-100 text-slate-700'
              }`}>
                {order.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Placed on {new Date(order.placed_at).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>

          {/* Prominent "Speak to Support" CTA */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <button
              onClick={() => setShowPreCall(true)}
              className="py-3 px-5 rounded-2xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm transition flex items-center justify-center gap-2.5 shadow-lg shadow-indigo-100 hover:scale-[1.02]"
            >
              <Mic className="w-4 h-4" />
              <span>Speak to Support</span>
            </button>

            <button
              onClick={() => {
                setShowPreCall(false);
                setActiveCallMode('text');
              }}
              className="py-2.5 px-3 rounded-2xl border border-slate-200 text-xs font-bold text-slate-600 hover:text-indigo-600 hover:bg-slate-50 transition flex items-center justify-center gap-1.5"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Prefer typing?</span>
            </button>
          </div>
        </div>

        {/* Product Details Section */}
        <div className="flex flex-col sm:flex-row gap-6 items-start">
          <div className="w-28 h-28 rounded-2xl overflow-hidden bg-slate-100 border border-slate-100 flex-shrink-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={item.image}
              alt={item.name}
              className="w-full h-full object-cover"
            />
          </div>

          <div className="flex-1 space-y-2">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 leading-snug">{item.name}</h2>
            <div className="flex flex-wrap gap-4 text-xs text-slate-500">
              <span>Qty: <strong className="text-slate-800">{item.quantity}</strong></span>
              <span>•</span>
              <span>Unit Price: <strong className="text-slate-800">₹{item.price.toLocaleString('en-IN')}</strong></span>
              <span>•</span>
              <span>Policy: <strong className={item.returnable ? "text-emerald-700" : "text-amber-700"}>{item.returnable ? "10-Day Returns" : "Non-Returnable"}</strong></span>
            </div>

            {order.delayed && (
              <div className="mt-3 px-3 py-2 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-800 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                <span>Delayed by {order.days_delayed} days beyond original ETA. Tap Speak to Support for instant voucher resolution.</span>
              </div>
            )}

            {order.replacement_requested && (
              <div className="mt-3 px-3 py-2 bg-emerald-50 rounded-xl border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>Replacement Confirmed ({order.replacement_order_id}) • Reference {order.replacement_id}</span>
              </div>
            )}
          </div>
        </div>

        {/* Tracking Timeline */}
        <div className="space-y-4 pt-4 border-t border-slate-100">
          <h3 className="text-sm font-extrabold text-slate-900 flex items-center gap-2">
            <Truck className="w-4 h-4 text-indigo-600" />
            <span>Delivery Timeline</span>
          </h3>

          <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
            {order.tracking.map((event, idx) => (
              <div key={idx} className="relative flex items-start justify-between gap-4">
                <span className="absolute -left-6 top-1 w-3 h-3 rounded-full bg-indigo-600 border-2 border-white ring-2 ring-indigo-100"></span>
                <div>
                  <p className="text-xs font-bold text-slate-900">{event.status}</p>
                  <p className="text-[11px] text-slate-500">{event.location}</p>
                </div>
                <span className="text-[10px] text-slate-400 font-mono">
                  {new Date(event.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Address and Payment Summary Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-6 border-t border-slate-100 text-xs">
          {/* Shipping Address */}
          <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-2">
            <div className="flex items-center gap-1.5 font-bold text-slate-900">
              <MapPin className="w-4 h-4 text-indigo-600" />
              <span>Delivery Address</span>
            </div>
            <p className="font-semibold text-slate-800">{order.customer.name}</p>
            <p className="text-slate-600 leading-relaxed">{order.customer.address}</p>
            <p className="text-slate-500">Phone: {order.customer.phone}</p>
          </div>

          {/* Payment Summary */}
          <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-2">
            <div className="flex items-center gap-1.5 font-bold text-slate-900">
              <CreditCard className="w-4 h-4 text-indigo-600" />
              <span>Payment Breakdown</span>
            </div>
            <div className="flex justify-between text-slate-600">
              <span>Item Subtotal</span>
              <span>₹{order.payment.subtotal.toLocaleString('en-IN')}</span>
            </div>
            <div className="flex justify-between text-slate-600">
              <span>Shipping</span>
              <span className="text-emerald-700 font-semibold">FREE</span>
            </div>
            <div className="flex justify-between font-bold text-slate-900 pt-1 border-t border-slate-200 text-sm">
              <span>Total Paid</span>
              <span>₹{order.payment.amount.toLocaleString('en-IN')}</span>
            </div>
            <p className="text-[11px] text-slate-500 pt-0.5">Method: {order.payment.method}</p>
          </div>
        </div>

      </div>

      {/* Pre-call Modal */}
      {showPreCall && (
        <PreCallModal
          customerName={order.customer.name}
          orderId={order.id}
          onClose={() => setShowPreCall(false)}
          onStartCall={(mode) => {
            setShowPreCall(false);
            setActiveCallMode(mode);
          }}
        />
      )}

      {/* Active Voice/Text Support Modal */}
      {activeCallMode && (
        <VoiceSupportModal
          order={order}
          initialMode={activeCallMode}
          onClose={() => setActiveCallMode(null)}
        />
      )}

      {/* Demo Presenter Controls */}
      <DemoPanel />
    </div>
  );
}

