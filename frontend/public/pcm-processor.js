class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(512); // 512 samples * 2 bytes = 1024 bytes
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0];
    // Input is float32 [-1.0, 1.0] at AudioContext sampleRate (typically 16000)
    for (let i = 0; i < channelData.length; i++) {
      let sample = Math.max(-1, Math.min(1, channelData[i]));
      // Convert to 16-bit PCM integer
      let int16 = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
      this.buffer[this.bufferIndex++] = int16;

      if (this.bufferIndex >= 512) {
        // Send a copy of the 1024-byte buffer
        const sendBuf = new Int16Array(this.buffer);
        this.port.postMessage(sendBuf.buffer, [sendBuf.buffer]);
        this.buffer = new Int16Array(512);
        this.bufferIndex = 0;
      }
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);

