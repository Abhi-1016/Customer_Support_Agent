'use client';

import { useEffect, useRef } from 'react';
import { CallState } from '@/lib/types';

interface AudioVisualizerProps {
  state: CallState;
  audioLevel: number; // 0.0 to 1.0
  isMuted: boolean;
}

export default function AudioVisualizer({ state, audioLevel, isMuted }: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    let phase = 0;

    const render = () => {
      phase += 0.05;
      const width = canvas.width;
      const height = canvas.height;
      const centerY = height / 2;

      ctx.clearRect(0, 0, width, height);

      // Pick stroke style based on state
      let color = '#94a3b8'; // idle / default
      let amplitude = 6;
      let bars = 32;

      if (state === 'speaking') {
        color = '#6366f1'; // Indigo for agent speaking
        amplitude = 12 + audioLevel * 35;
      } else if (state === 'listening' && !isMuted) {
        color = '#06b6d4'; // Cyan for user listening
        amplitude = 8 + audioLevel * 25;
      } else if (state === 'thinking') {
        color = '#a855f7'; // Purple for thinking
        amplitude = 10 + Math.sin(phase * 2) * 8;
      } else if (state === 'connecting' || state === 'reconnecting') {
        color = '#f59e0b'; // Amber for connecting
        amplitude = 5 + Math.sin(phase) * 5;
      }

      // Draw multi-bar equalizer wave
      const barWidth = width / bars;
      for (let i = 0; i < bars; i++) {
        const x = i * barWidth;
        const distFromCenter = Math.abs(i - bars / 2) / (bars / 2);
        const weight = Math.cos(distFromCenter * (Math.PI / 2));
        
        const wave = Math.sin(phase + i * 0.3) * amplitude * weight;
        const barHeight = Math.max(4, Math.abs(wave) * 2);

        ctx.fillStyle = color;
        ctx.beginPath();
        // Rounded bar
        ctx.roundRect(x + 2, centerY - barHeight / 2, barWidth - 4, barHeight, 4);
        ctx.fill();
      }

      animationId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [state, audioLevel, isMuted]);

  return (
    <div className="w-full flex flex-col items-center justify-center p-3">
      <canvas
        ref={canvasRef}
        width={360}
        height={80}
        className="w-full max-w-[360px] h-[80px]"
      />
    </div>
  );
}

