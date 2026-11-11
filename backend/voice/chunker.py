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
        start_idx = 0

        while True:
            # Look for sentence boundary: punctuation followed by space or newline, or newline
            match = re.search(r'([.!?]+(?:\s+|\n+))|(\n+)', self.buffer[start_idx:])
            if not match:
                break

            match_end = start_idx + match.end()
            candidate = self.buffer[:match_end].strip()

            # Check if this period was part of an abbreviation or decimal number
            words = candidate.split()
            last_word = words[-1].lower() if words else ""
            if last_word in ABBREVIATIONS or re.search(r'\d+\.\d*$', candidate):
                # Search past this abbreviation
                start_idx = match_end
                continue

            if candidate:
                sentences.append(candidate)
            self.buffer = self.buffer[match_end:].lstrip()
            start_idx = 0

        return sentences

    def flush(self) -> List[str]:
        """Flush any remaining text in the buffer as the final sentence."""
        remaining = self.buffer.strip()
        self.buffer = ""
        if remaining:
            return [remaining]
        return []

