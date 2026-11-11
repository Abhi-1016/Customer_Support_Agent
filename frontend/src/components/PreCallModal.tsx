'use client';

import { useState, useEffect } from 'react';
import { Mic, ShieldCheck, AlertCircle, Volume2, ArrowRight, X } from 'lucide-react';

interface PreCallModalProps {
  onStartCall: (mode: 'voice' | 'text') => void;
  onClose: () => void;
  customerName: string;
  orderId: string;
}

export default function PreCallModal({ onStartCall, onClose, customerName, orderId }: PreCallModalProps) {
  const [micStatus, setMicStatus] = useState<'checking' | 'granted' | 'denied' | 'unsupported'>('checking');
  const [micLevel, setMicLevel] = useState(0);
  const [testingMic, setTestingMic] = useState(false);

  useEffect(() => {
    // Check browser support
    if (typeof window === 'undefined') return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.AudioContext) {
      setMicStatus('unsupported');
      return;
    }

    // Check permission status
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'microphone' as PermissionName }).then((res) => {
        if (res.state === 'granted') setMicStatus('granted');
        else if (res.state === 'denied') setMicStatus('denied');
        else setMicStatus('checking');
      }).catch(() => {
        setMicStatus('checking');
      });
    } else {
      setMicStatus('checking');
    }
  }, []);

  const testMicPermission = async () => {
    setTestingMic(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      setMicStatus('granted');

      // 2-second mic level feedback test
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);

      const buffer = new Uint8Array(analyser.frequencyBinCount);
      let frames = 0;
      const interval = setInterval(() => {
        analyser.getByteFrequencyData(buffer);
        let sum = 0;
        for (let i = 0; i < buffer.length; i++) sum += buffer[i];
        setMicLevel(Math.min(100, Math.round((sum / buffer.length) * 1.5)));
        frames++;
        if (frames > 20) {
          clearInterval(interval);
          stream.getTracks().forEach(t => t.stop());
          audioCtx.close();
          setTestingMic(false);
        }
      }, 100);

    } catch (err: any) {
      setTestingMic(false);
      setMicStatus('denied');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden">
        {/* Header */}
        <div className="p-6 pb-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <Mic className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-extrabold text-slate-900">Start Voice Support</h2>
              <p className="text-xs text-slate-500 font-mono">Order {orderId}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          {/* Friendly explainer & consent */}
          <div className="p-4 rounded-2xl bg-indigo-50/70 border border-indigo-100/80 text-xs text-indigo-950 space-y-1.5 leading-relaxed">
            <div className="flex items-center gap-2 font-bold text-indigo-900">
              <ShieldCheck className="w-4 h-4 text-indigo-600 flex-shrink-0" />
              <span>Consent & Privacy Notice</span>
            </div>
            <p className="text-indigo-900/80">
              This call is handled by Maya, an AI assistant, and a live transcript is saved to help resolve your issue. You can interrupt or switch to typed chat at any time.
            </p>
          </div>

          {/* Mic permission status */}
          {micStatus === 'denied' ? (
            <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 text-xs text-rose-900 space-y-2">
              <div className="flex items-center gap-2 font-bold text-rose-700">
                <AlertCircle className="w-4 h-4 text-rose-600" />
                <span>Microphone access was blocked</span>
              </div>
              <p>
                To speak with Maya, click the camera/microphone icon in your browser address bar and choose &quot;Allow&quot;. Or continue in typed chat mode right now.
              </p>
            </div>
          ) : micStatus === 'unsupported' ? (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-2">
              <div className="flex items-center gap-2 font-bold text-amber-800">
                <AlertCircle className="w-4 h-4 text-amber-600" />
                <span>Voice audio not supported in this browser</span>
              </div>
              <p>Your browser does not support the required Web Audio APIs. You can still use full typed chat support.</p>
            </div>
          ) : (
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700 flex items-center gap-2">
                  <Volume2 className="w-4 h-4 text-slate-500" />
                  Microphone Check
                </span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                  micStatus === 'granted' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'
                }`}>
                  {micStatus === 'granted' ? 'Ready' : 'Not tested'}
                </span>
              </div>

              {testingMic && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-slate-500">
                    <span>Say hello...</span>
                    <span>{micLevel}%</span>
                  </div>
                  <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                    <div className="bg-emerald-500 h-full transition-all duration-100" style={{ width: `${micLevel}%` }}></div>
                  </div>
                </div>
              )}

              {micStatus !== 'granted' && (
                <button
                  type="button"
                  onClick={testMicPermission}
                  disabled={testingMic}
                  className="w-full py-2 bg-white border border-slate-300 hover:border-indigo-400 rounded-xl text-xs font-bold text-slate-700 hover:text-indigo-600 transition shadow-sm"
                >
                  {testingMic ? 'Listening...' : 'Test Microphone'}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-6 pt-3 border-t border-slate-100 flex flex-col sm:flex-row items-center gap-3">
          <button
            type="button"
            onClick={() => onStartCall('text')}
            className="w-full sm:w-1/2 py-3 px-4 rounded-2xl border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50 transition"
          >
            Prefer typing? Continue in Chat
          </button>

          <button
            type="button"
            onClick={() => onStartCall('voice')}
            disabled={micStatus === 'denied' || micStatus === 'unsupported'}
            className="w-full sm:w-1/2 py-3 px-4 rounded-2xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-bold transition flex items-center justify-center gap-2 shadow-md shadow-indigo-100"
          >
            <span>Start Voice Call</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

