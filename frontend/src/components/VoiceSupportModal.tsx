'use client';

import React, { useState, useEffect, useRef } from 'react';
import { 
  X, Mic, MicOff, Send, Check, PhoneOff, AlertCircle, Copy, 
  Star, ChevronDown, Sparkles, MessageSquare, ShieldCheck, CheckCircle2 
} from 'lucide-react';
import { Order, CallState, TranscriptBubble, CallSummaryData } from '@/lib/types';
import AudioVisualizer from './AudioVisualizer';

interface VoiceSupportModalProps {
  order: Order;
  initialMode: 'voice' | 'text';
  onClose: () => void;
}

export default function VoiceSupportModal({ order, initialMode, onClose }: VoiceSupportModalProps) {
  // Session & WebSocket state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [callState, setCallState] = useState<CallState>('connecting');
  const [language, setLanguage] = useState<'en-IN' | 'hi-IN'>('en-IN');
  // Auto-mute: starts muted while Maya delivers her initial 1-line greeting
  const [isMuted, setIsMuted] = useState(true);
  const [pushToTalk, setPushToTalk] = useState(false);
  const [isPressingPTT, setIsPressingPTT] = useState(false);

  // Synchronized refs to avoid stale closure in AudioWorklet onmessage callback
  const callStateRef = useRef<CallState>('connecting');
  const isMutedRef = useRef(true);
  const pushToTalkRef = useRef(false);
  const isPressingPTTRef = useRef(false);

  const updateMute = (muted: boolean) => {
    isMutedRef.current = muted;
    setIsMuted(muted);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ event: muted ? 'mute' : 'unmute' }));
    }
  };

  const updatePushToTalk = (ptt: boolean) => {
    pushToTalkRef.current = ptt;
    setPushToTalk(ptt);
  };

  const updateIsPressingPTT = (pressing: boolean) => {
    isPressingPTTRef.current = pressing;
    setIsPressingPTT(pressing);
  };

  // Audio level & visualizer
  const [audioLevel, setAudioLevel] = useState(0);

  // Rolling transcript
  const [transcript, setTranscript] = useState<TranscriptBubble[]>([]);
  const [currentToolAction, setCurrentToolAction] = useState<string | null>(null);
  const [agentTyping, setAgentTyping] = useState(false);

  // Text input
  const [inputText, setInputText] = useState('');

  // Confirmation Card
  const [confirmationRequest, setConfirmationRequest] = useState<{
    action_id: string;
    summary: string;
    details: any;
  } | null>(null);

  // End of call summary
  const [callSummary, setCallSummary] = useState<CallSummaryData | null>(null);
  const [rating, setRating] = useState<number>(5);
  const [comment, setComment] = useState('');
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Degradation / error notice
  const [warningBanner, setWarningBanner] = useState<string | null>(null);

  // Refs for Web Audio & WebSocket
  const wsRef = useRef<WebSocket | null>(null);
  const micAudioContextRef = useRef<AudioContext | null>(null);
  const playbackAudioContextRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const audioQueueRef = useRef<AudioBufferSourceNode[]>([]);
  const nextPlayTimeRef = useRef<number>(0);
  const transcriptBottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript, agentTyping, currentToolAction]);

  // Audio Context unlocker helper
  const ensureAudioResumed = async () => {
    try {
      if (micAudioContextRef.current && micAudioContextRef.current.state === 'suspended') {
        await micAudioContextRef.current.resume();
      }
      if (playbackAudioContextRef.current && playbackAudioContextRef.current.state === 'suspended') {
        await playbackAudioContextRef.current.resume();
      }
    } catch (e) {}
  };

  // Keyboard spacebar listener for Push-to-Talk
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && pushToTalkRef.current && !e.repeat) {
        const target = e.target as HTMLElement;
        if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
          e.preventDefault();
          ensureAudioResumed();
          updateIsPressingPTT(true);
        }
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && pushToTalkRef.current) {
        const target = e.target as HTMLElement;
        if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
          e.preventDefault();
          updateIsPressingPTT(false);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  // 1. Initialize Support Session with Backend
  useEffect(() => {
    let isCancelled = false;

    const startSession = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/support/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ order_id: order.id, language })
        });
        if (!res.ok) throw new Error('Failed to create support session');
        const data = await res.json();
        if (isCancelled) return;

        setSessionId(data.session_id);
        connectWebSocket(data.session_id, data.token);
      } catch (err: any) {
        setCallState('ended');
        setWarningBanner('Unable to establish connection to support servers. Please try again.');
      }
    };

    startSession();

    return () => {
      isCancelled = true;
      teardown();
    };
  }, []);

  // 2. Connect WebSocket
  const connectWebSocket = (sessId: string, token: string) => {
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
    const ws = new WebSocket(`${wsBase}/ws/call/${sessId}?token=${token}`);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      setCallState('listening');
      // If voice mode, initialize mic pipeline (starts muted until Maya finishes greeting)
      if (initialMode === 'voice') {
        startMicPipeline();
      }
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary frame = raw PCM audio chunk from backend TTS (24kHz 16-bit mono)
        playAudioChunk(event.data);
      } else {
        // JSON event
        try {
          const msg = JSON.parse(event.data);
          handleServerEvent(msg);
        } catch (e) {
          console.error('Error parsing JSON from WS', e);
        }
      }
    };

    ws.onerror = () => {
      setCallState('reconnecting');
    };

    ws.onclose = () => {
      if (callState !== 'ended') {
        setCallState('reconnecting');
        setTimeout(() => {
          if (sessionId) connectWebSocket(sessionId, token);
        }, 2000);
      }
    };
  };

  // 3. Handle Server Events with Turn-Taking
  const handleServerEvent = (msg: any) => {
    switch (msg.event) {
      case 'ready':
        callStateRef.current = 'listening';
        setCallState('listening');
        break;

      case 'state':
        callStateRef.current = msg.state;
        setCallState(msg.state);
        if (msg.state === 'speaking' || msg.state === 'thinking' || msg.state === 'connecting') {
          setAgentTyping(false);
          // Turn-taking: strictly mute mic while Maya is thinking or speaking
          updateMute(true);
        } else if (msg.state === 'listening') {
          // If in voice mode and playback queue has emptied, unmute customer mic after 300ms acoustic grace period
          if (initialMode === 'voice' && audioQueueRef.current.length === 0) {
            setTimeout(() => {
              if (audioQueueRef.current.length === 0 && callStateRef.current === 'listening') {
                updateMute(false);
              }
            }, 300);
          }
        } else if (msg.state === 'ended') {
          updateMute(true);
        }
        break;

      case 'user_transcript':
        // Customer finished utterance -> mute mic while agent processes
        updateMute(true);
        setTranscript((prev) => [
          ...prev,
          {
            id: `usr-${Date.now()}`,
            speaker: 'customer',
            text: msg.text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            interrupted: false
          }
        ]);
        setAgentTyping(true);
        break;

      case 'agent_sentence':
        setAgentTyping(false);
        // Ensure mic is muted during speech playback
        updateMute(true);
        setTranscript((prev) => [
          ...prev,
          {
            id: msg.id || `agt-${Date.now()}`,
            speaker: 'agent',
            text: msg.text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            interrupted: false
          }
        ]);
        break;

      case 'agent_interrupted':
        clearAudioQueue();
        if (initialMode === 'voice') {
          updateMute(false);
        }
        setTranscript((prev) => {
          if (prev.length === 0) return prev;
          const updated = [...prev];
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].speaker === 'agent') {
              updated[i] = { ...updated[i], interrupted: true };
              break;
            }
          }
          return updated;
        });
        break;

      case 'tool_started':
        setCurrentToolAction(msg.name);
        break;

      case 'tool_result':
        setCurrentToolAction(null);
        setTranscript((prev) => [
          ...prev,
          {
            id: `tool-${Date.now()}`,
            speaker: 'system',
            text: msg.summary,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            action_chip: msg.summary
          }
        ]);
        break;

      case 'confirmation_request':
        setConfirmationRequest({
          action_id: msg.action_id,
          summary: msg.summary,
          details: msg.details || {}
        });
        break;

      case 'call_summary':
        callStateRef.current = 'ended';
        setCallState('ended');
        setCallSummary(msg.summary);
        updateMute(true);
        // Ensure feedback card is smoothly scrolled into view
        setTimeout(() => {
          transcriptBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 150);
        break;

      case 'error':
        if (msg.code === 'VOICE_UNAVAILABLE') {
          setWarningBanner('Voice audio is currently unavailable. Switched to typed chat mode.');
          updateMute(true);
        } else {
          setWarningBanner(msg.user_message);
        }
        break;

      default:
        break;
    }
  };

  // 4. Microphone AudioWorklet Setup (16kHz PCM capture in 1024-byte frames)
  const startMicPipeline = async () => {
    try {
      if (micStreamRef.current) return;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      micStreamRef.current = stream;

      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 16000
      });
      micAudioContextRef.current = audioCtx;

      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }

      // Load PCM processor worklet
      await audioCtx.audioWorklet.addModule('/pcm-processor.js');
      const workletNode = new AudioWorkletNode(audioCtx, 'pcm-processor');
      workletNodeRef.current = workletNode;

      // Handle raw PCM frames from worklet using refs to ensure live state
      workletNode.port.onmessage = (e) => {
        const pcmBuffer = e.data; // ArrayBuffer (1024 bytes)
        // Auto-mute: if muted, do not send audio to STT
        if (isMutedRef.current || (pushToTalkRef.current && !isPressingPTTRef.current)) {
          setAudioLevel(0);
          return;
        }

        const int16s = new Int16Array(pcmBuffer);
        let sum = 0;
        for (let i = 0; i < int16s.length; i++) {
          sum += Math.abs(int16s[i]);
        }
        const avg = sum / int16s.length;
        // Dynamic mic sensitivity for visualizer
        setAudioLevel(Math.min(1.0, avg / 2500));

        // Send binary frame to backend WebSocket
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(pcmBuffer);
        }
      };

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(workletNode);
      // Connect to a 0-gain node terminating at destination to keep AudioWorklet alive in Chromium without audio feedback
      const muteGain = audioCtx.createGain();
      muteGain.gain.setValueAtTime(0, audioCtx.currentTime);
      workletNode.connect(muteGain);
      muteGain.connect(audioCtx.destination);
    } catch (err: any) {
      console.warn('Microphone start error:', err);
      setWarningBanner('Microphone unavailable. Continuing in text chat mode.');
      updateMute(true);
    }
  };

  // 5. High-Clarity Web Audio Playback Queue (24kHz 16-bit PCM)
  const playAudioChunk = (pcmArrayBuffer: ArrayBuffer) => {
    if (!playbackAudioContextRef.current || playbackAudioContextRef.current.state === 'closed') {
      playbackAudioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    const audioCtx = playbackAudioContextRef.current;
    if (audioCtx.state === 'suspended') audioCtx.resume();

    // Matching exact 24,000 Hz synthesis rate from Gnani Devika voice
    const sampleRate = 24000;
    const int16Array = new Int16Array(pcmArrayBuffer);
    const float32Array = new Float32Array(int16Array.length);

    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const audioBuffer = audioCtx.createBuffer(1, float32Array.length, sampleRate);
    audioBuffer.copyToChannel(float32Array, 0);

    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioCtx.destination);

    const currentTime = audioCtx.currentTime;
    const startTime = Math.max(currentTime, nextPlayTimeRef.current);
    source.start(startTime);
    nextPlayTimeRef.current = startTime + audioBuffer.duration;

    audioQueueRef.current.push(source);
    setAudioLevel(0.85);

    // Turn-taking: mic stays muted during speech
    updateMute(true);

    source.onended = () => {
      audioQueueRef.current = audioQueueRef.current.filter((s) => s !== source);
      if (audioQueueRef.current.length === 0) {
        setAudioLevel(0);
        // Playback has physically finished in user's speaker!
        // Automatically unmute customer's mic only if backend is finished (listening)
        if (initialMode === 'voice' && callStateRef.current === 'listening') {
          setTimeout(() => {
            if (audioQueueRef.current.length === 0 && callStateRef.current === 'listening') {
              updateMute(false);
            }
          }, 300);
        }
      }
    };
  };

  const clearAudioQueue = () => {
    audioQueueRef.current.forEach((src) => {
      try { src.stop(); } catch (e) {}
    });
    audioQueueRef.current = [];
    nextPlayTimeRef.current = 0;
    setAudioLevel(0);
  };

  // 6. Barge-in & Interruption
  const triggerBargeIn = () => {
    clearAudioQueue();
    if (initialMode === 'voice') {
      updateMute(false);
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ event: 'barge_in' }));
    }
  };

  // 7. Send text message
  const handleSendText = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    if (callState === 'speaking') {
      triggerBargeIn();
    }

    updateMute(true); // Customer just sent input, mute mic while Maya replies
    wsRef.current.send(JSON.stringify({
      event: 'text_message',
      text: inputText.trim()
    }));
    setInputText('');
  };

  // 8. Confirm action card decision
  const handleConfirmDecision = (decision: boolean) => {
    if (!confirmationRequest || !wsRef.current) return;
    updateMute(true);
    wsRef.current.send(JSON.stringify({
      event: 'confirm_action',
      action_id: confirmationRequest.action_id,
      decision: decision
    }));
    setConfirmationRequest(null);
  };

  // 9. End Call
  const handleEndCall = () => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ event: 'end_call' }));
    }
    clearAudioQueue();
    updateMute(true);
    setCallState('ended');
  };

  // 10. Submit Feedback
  const handleSubmitFeedback = async () => {
    if (!sessionId) return;
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      await fetch(`${apiUrl}/api/support/sessions/${sessionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating, comment })
      });
      setFeedbackSubmitted(true);
    } catch (e) {
      console.error('Error submitting feedback', e);
    }
  };

  const copyToClipboard = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const teardown = () => {
    clearAudioQueue();
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
    }
    if (micAudioContextRef.current && micAudioContextRef.current.state !== 'closed') {
      micAudioContextRef.current.close();
    }
    if (playbackAudioContextRef.current && playbackAudioContextRef.current.state !== 'closed') {
      playbackAudioContextRef.current.close();
    }
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  return (
    <div 
      onClick={ensureAudioResumed}
      className="fixed inset-0 z-50 flex items-center justify-center p-0 sm:p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
    >
      <div className="w-full h-full sm:h-auto sm:max-h-[92vh] sm:max-w-2xl bg-white sm:rounded-3xl shadow-2xl flex flex-col overflow-hidden border border-slate-200">
        
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between bg-white z-10">
          <div className="flex items-center gap-3 min-w-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={order.items[0].image}
              alt=""
              className="w-10 h-10 rounded-xl object-cover border border-slate-100 flex-shrink-0"
            />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold text-slate-900">{order.id}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 font-semibold text-slate-700">
                  {order.status}
                </span>
              </div>
              <p className="text-xs text-slate-500 truncate max-w-[200px] sm:max-w-[280px]">
                {order.items[0].name}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as any)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 font-semibold text-slate-700 focus:outline-none"
            >
              <option value="en-IN">English (IN)</option>
              <option value="hi-IN">Hindi (हिंदी)</option>
            </select>

            <button
              onClick={handleEndCall}
              className="p-2 rounded-xl text-rose-600 hover:bg-rose-50 transition"
              title="End Support Call"
            >
              <PhoneOff className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Warning / Notice banner */}
        {warningBanner && (
          <div className="px-4 py-2 bg-amber-50 border-b border-amber-200/80 text-xs text-amber-900 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span>{warningBanner}</span>
          </div>
        )}

        {/* Visualizer & Agent State Indicator */}
        <div className="bg-gradient-to-b from-slate-50 to-white px-4 py-3 border-b border-slate-100 flex flex-col items-center">
          <div className="flex items-center gap-2 mb-1">
            <span className={`w-2.5 h-2.5 rounded-full ${
              callState === 'speaking' ? 'bg-indigo-500 animate-pulse' :
              callState === 'listening' ? 'bg-cyan-500 animate-pulse' :
              callState === 'thinking' ? 'bg-purple-500 animate-bounce' :
              callState === 'reconnecting' ? 'bg-amber-500 animate-spin' :
              callState === 'ended' ? 'bg-slate-400' : 'bg-emerald-500'
            }`} />
            <span className="text-xs font-bold capitalize text-slate-700 tracking-wide">
              {callState === 'speaking' ? 'Maya is speaking… (Mic Muted)' :
               callState === 'listening' ? (isMuted ? 'Muted (Tap to speak)' : 'Listening to you… (Take your time, speak whenever ready)') :
               callState === 'thinking' ? 'Analyzing your response… (Mic Muted)' :
               callState === 'reconnecting' ? 'Reconnecting session…' :
               callState === 'ended' ? 'Call Ended' : 'Connecting…'}
            </span>
          </div>

          <AudioVisualizer state={callState} audioLevel={audioLevel} isMuted={isMuted} />
        </div>

        {/* Rolling Transcript Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 bg-slate-50/50">
          {transcript.length === 0 && (
            <div className="h-48 flex flex-col items-center justify-center text-center text-slate-400 space-y-2">
              <Sparkles className="w-8 h-8 text-indigo-400" />
              <p className="text-xs font-medium">Maya is starting your support call...</p>
            </div>
          )}

          {transcript.map((bubble) => {
            if (bubble.speaker === 'system') {
              return (
                <div key={bubble.id} className="flex justify-center my-2">
                  <div className="px-3 py-1.5 rounded-full bg-indigo-50 border border-indigo-100/80 text-[11px] font-semibold text-indigo-700 flex items-center gap-1.5 shadow-sm">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                    <span>{bubble.action_chip || bubble.text}</span>
                  </div>
                </div>
              );
            }

            const isAgent = bubble.speaker === 'agent';
            return (
              <div
                key={bubble.id}
                className={`flex flex-col ${isAgent ? 'items-start' : 'items-end'} space-y-1`}
              >
                <div className="flex items-center gap-1 px-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    {isAgent ? 'Maya (Support)' : 'You'}
                  </span>
                  <span className="text-[10px] text-slate-300">•</span>
                  <span className="text-[10px] text-slate-400">{bubble.timestamp}</span>
                </div>

                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed shadow-sm ${
                    isAgent
                      ? 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm'
                      : 'bg-indigo-600 text-white rounded-tr-sm'
                  }`}
                >
                  <p>{bubble.text}</p>
                  {bubble.interrupted && (
                    <span className="inline-block mt-1 text-[10px] font-bold text-amber-500 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                      Interrupted
                    </span>
                  )}
                </div>
              </div>
            );
          })}

          {/* Inline Action Indicator */}
          {currentToolAction && (
            <div className="flex items-center gap-2 text-xs font-semibold text-indigo-600 bg-indigo-50/80 px-3 py-2 rounded-xl border border-indigo-100 w-fit animate-pulse">
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
              <span>{currentToolAction}</span>
            </div>
          )}

          {/* Confirmation Card Popup */}
          {confirmationRequest && (
            <div className="p-4 rounded-2xl bg-white border-2 border-indigo-500 shadow-lg space-y-3 animate-fade-in my-3">
              <div className="flex items-center gap-2 text-indigo-900 font-bold text-xs">
                <CheckCircle2 className="w-4 h-4 text-indigo-600" />
                <span>Confirmation Requested</span>
              </div>
              <p className="text-xs text-slate-700">{confirmationRequest.summary}</p>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={() => handleConfirmDecision(true)}
                  className="flex-1 py-2 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition shadow-sm"
                >
                  Confirm (Yes)
                </button>
                <button
                  onClick={() => handleConfirmDecision(false)}
                  className="py-2 px-3 rounded-xl border border-slate-300 text-slate-700 text-xs font-bold hover:bg-slate-50 transition"
                >
                  Change
                </button>
              </div>
            </div>
          )}

          {/* End-of-Call Summary Card */}
          {callSummary && (
            <div className="p-5 rounded-3xl bg-white border border-slate-200 shadow-md space-y-4 my-4 animate-fade-in">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                    <Check className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-extrabold text-slate-900">Call Summary & Receipt</h3>
                    <p className="text-[10px] text-slate-500">Duration: {callSummary.duration_seconds}s</p>
                  </div>
                </div>
                <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                  callSummary.resolution === 'resolved' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
                  callSummary.resolution === 'escalated' ? 'bg-amber-50 text-amber-700 border border-amber-200' :
                  'bg-slate-100 text-slate-700'
                }`}>
                  {callSummary.resolution.toUpperCase()}
                </span>
              </div>

              <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 p-3 rounded-2xl">
                {callSummary.summary_text}
              </p>

              {Object.keys(callSummary.reference_ids).length > 0 && (
                <div className="space-y-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Reference Numbers</span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {Object.entries(callSummary.reference_ids).map(([key, val]) => (
                      <div key={key} className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200 bg-white">
                        <div className="min-w-0">
                          <p className="text-[10px] text-slate-400 capitalize">{key.replace('_', ' ')}</p>
                          <p className="font-mono text-xs font-bold text-slate-900 truncate">{val}</p>
                        </div>
                        <button
                          onClick={() => copyToClipboard(key, val)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition"
                        >
                          {copiedKey === key ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 1 to 5 Star Rating */}
              <div className="p-4 rounded-2xl bg-indigo-50/50 border border-indigo-100/60 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-800">How was this call?</span>
                  <div className="flex items-center gap-1">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <button
                        key={star}
                        onClick={() => setRating(star)}
                        className="p-1 hover:scale-110 transition"
                      >
                        <Star className={`w-4 h-4 ${star <= rating ? 'fill-amber-400 text-amber-400' : 'text-slate-300'}`} />
                      </button>
                    ))}
                  </div>
                </div>

                {!feedbackSubmitted ? (
                  <div className="space-y-2">
                    <input
                      type="text"
                      placeholder="Optional feedback comment..."
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      className="w-full px-3 py-1.5 text-xs bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      onClick={handleSubmitFeedback}
                      className="w-full py-2 bg-indigo-600 text-white rounded-xl text-xs font-bold hover:bg-indigo-700 transition"
                    >
                      Submit Feedback
                    </button>
                  </div>
                ) : (
                  <p className="text-xs text-emerald-700 font-semibold text-center">Thank you for your feedback!</p>
                )}
              </div>

              <button
                onClick={onClose}
                className="w-full py-3 rounded-2xl bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 transition shadow-sm"
              >
                Back to Order Details
              </button>
            </div>
          )}

          <div ref={transcriptBottomRef} />
        </div>

        {/* Bottom Controls & Text Input */}
        {callState !== 'ended' && (
          <div className="p-3 sm:p-4 bg-white border-t border-slate-100 space-y-3">
            {/* Mic & Turn Status Row */}
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={async () => {
                    await ensureAudioResumed();
                    updateMute(!isMutedRef.current);
                  }}
                  className={`p-3 rounded-2xl font-bold flex items-center gap-2 transition ${
                    isMuted
                      ? 'bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100'
                      : 'bg-emerald-50 text-emerald-800 border border-emerald-200 hover:bg-emerald-100'
                  }`}
                >
                  {isMuted ? <MicOff className="w-4 h-4 text-amber-600" /> : <Mic className="w-4 h-4 text-emerald-600" />}
                  <span className="text-xs">{isMuted ? 'Mic Muted (Auto)' : 'Mic Active (Speak Now)'}</span>
                </button>

                <button
                  type="button"
                  onClick={async () => {
                    await ensureAudioResumed();
                    updatePushToTalk(!pushToTalkRef.current);
                  }}
                  className={`px-3 py-2 rounded-xl text-xs font-bold border transition ${
                    pushToTalk
                      ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {pushToTalk ? 'Push-to-Talk (Active)' : 'Hands-free VAD'}
                </button>
              </div>

              {callState === 'speaking' && (
                <button
                  type="button"
                  onClick={triggerBargeIn}
                  className="px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs font-bold hover:bg-amber-100 transition"
                >
                  Interrupt Maya
                </button>
              )}
            </div>

            {/* PTT Press Button if PTT mode is active */}
            {pushToTalk && (
              <button
                type="button"
                onMouseDown={async () => {
                  await ensureAudioResumed();
                  updateIsPressingPTT(true);
                }}
                onMouseUp={() => updateIsPressingPTT(false)}
                onTouchStart={async () => {
                  await ensureAudioResumed();
                  updateIsPressingPTT(true);
                }}
                onTouchEnd={() => updateIsPressingPTT(false)}
                className={`w-full py-3 rounded-2xl text-xs font-bold uppercase tracking-wider transition select-none ${
                  isPressingPTT ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {isPressingPTT ? 'Listening (Release to send)...' : 'Hold to Speak (or hold Spacebar)'}
              </button>
            )}

            {/* Typed Chat Input Box */}
            <form onSubmit={handleSendText} className="flex gap-2">
              <input
                type="text"
                placeholder="Type a message to Maya anytime..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-2xl text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition"
              />
              <button
                type="submit"
                disabled={!inputText.trim()}
                className="p-2.5 rounded-2xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white transition shadow-sm"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
