import re
from typing import AsyncIterator, List

# Common abbreviations that should NOT trigger a sentence split
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "e.g.", "i.e.", "vs.", "approx.", "etc.", "no.", "rs.", "st."
}

class SentenceChunker:
    def __init__(self):
        self.buffer = ""

    def add_token(self, token: str) -> List[str]:
        """Add a token to the buffer and return any completed sentences."""
        self.buffer += token
        sentences = []

        while True:
            # Look for sentence boundary: punctuation followed by space or newline, or newline
            match = re.search(r'([.!?]+(?:\s+|\n+))|(\n+)', self.buffer)
            if not match:
                break

            split_pos = match.end()
            candidate = self.buffer[:split_pos].strip()

            # Check if this period was part of an abbreviation or decimal number
            last_word = candidate.split()[-1].lower() if candidate.split() else ""
            if last_word in ABBREVIATIONS or re.search(r'\d+\.\d*$', candidate):
                # Not a true sentence boundary; continue looking further in buffer
                # If there is nothing else in buffer, break and wait for more tokens
                rest = self.buffer[split_pos:]
                next_match = re.search(r'([.!?]+(?:\s+|\n+))|(\n+)', rest)
                if not next_match:
                    break
                split_pos += next_match.end()
                candidate = self.buffer[:split_pos].strip()

            if candidate:
                sentences.append(candidate)
            self.buffer = self.buffer[split_pos:].lstrip()

        return sentences

    def flush(self) -> List[str]:
        """Flush any remaining text in the buffer as the final sentence."""
        remaining = self.buffer.strip()
        self.buffer = ""
        if remaining:
            return [remaining]
        return []

