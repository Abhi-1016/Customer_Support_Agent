'use client';

import { useState } from 'react';
import { Sliders, AlertOctagon, Check } from 'lucide-react';

interface DemoPanelProps {
  sessionId?: string | null;
}

export default function DemoPanel({ sessionId }: DemoPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [killTTS, setKillTTS] = useState(false);
  const [forceSlotFull, setForceSlotFull] = useState(false);
  const [forcePickupFail, setForcePickupFail] = useState(false);
  const [forceRefundFail, setForceRefundFail] = useState(false);
  const [applied, setApplied] = useState(false);

  const applyConfig = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      await fetch(`${apiUrl}/api/admin/demo_mode?kill_tts=${killTTS}&force_slot_full=${forceSlotFull}&force_pickup_fail=${forcePickupFail}&force_refund_fail=${forceRefundFail}${sessionId ? `&session_id=${sessionId}` : ''}`, {
        method: 'POST'
      });
      setApplied(true);
      setTimeout(() => setApplied(false), 2000);
    } catch (e) {
      console.error('Failed to configure demo mode', e);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {!isOpen ? (
        <button
          onClick={() => setIsOpen(true)}
          className="p-3 bg-slate-900 text-white rounded-2xl shadow-xl hover:bg-slate-800 transition flex items-center gap-2 text-xs font-bold border border-slate-700"
          title="Presenter Demo Debug Panel"
        >
          <Sliders className="w-4 h-4 text-indigo-400" />
          <span>Demo Controls</span>
        </button>
      ) : (
        <div className="w-72 bg-slate-900 border border-slate-700 text-white rounded-3xl p-5 shadow-2xl space-y-4 animate-fade-in text-xs">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="font-extrabold flex items-center gap-2 text-indigo-300">
              <AlertOctagon className="w-4 h-4 text-indigo-400" />
              Demo Failure Controls
            </span>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-white transition"
            >
              ✕
            </button>
          </div>

          <div className="space-y-2.5">
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Simulate TTS Crash (Cascade to Text)</span>
              <input
                type="checkbox"
                checked={killTTS}
                onChange={(e) => setKillTTS(e.target.checked)}
                className="rounded accent-indigo-500"
              />
            </label>

            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Simulate Pickup Slot Full</span>
              <input
                type="checkbox"
                checked={forceSlotFull}
                onChange={(e) => setForceSlotFull(e.target.checked)}
                className="rounded accent-indigo-500"
              />
            </label>

            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Simulate Pickup Failure</span>
              <input
                type="checkbox"
                checked={forcePickupFail}
                onChange={(e) => setForcePickupFail(e.target.checked)}
                className="rounded accent-indigo-500"
              />
            </label>

            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-slate-300">Simulate Refund Failure</span>
              <input
                type="checkbox"
                checked={forceRefundFail}
                onChange={(e) => setForceRefundFail(e.target.checked)}
                className="rounded accent-indigo-500"
              />
            </label>
          </div>

          <button
            onClick={applyConfig}
            className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-xl transition flex items-center justify-center gap-1.5"
          >
            {applied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : null}
            <span>{applied ? 'Simulations Applied' : 'Apply Failure Hooks'}</span>
          </button>
        </div>
      )}
    </div>
  );
}

