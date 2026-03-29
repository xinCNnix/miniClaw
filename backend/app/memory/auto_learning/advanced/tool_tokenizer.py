"""Tool call tokenizer for TrajectoryEncoder input."""

import torch

TOOL_VOCAB = {
    "terminal": 1, "python_repl": 2, "fetch_url": 3,
    "read_file": 4, "write_file": 5, "search_kb": 6,
}
PAD = 0
SUCCESS = 10
FAILURE = 11
SEP = 12
UNK = 99
MAX_SEQ_LEN = 128


def tokenize_tool_calls(tool_calls: list[dict]) -> torch.Tensor:
    """Convert tool call sequence to padded token IDs tensor.

    Args:
        tool_calls: List of dicts with keys 'name' (str) and 'success' (bool).

    Returns:
        torch.Tensor of shape [MAX_SEQ_LEN] with dtype long.
    """
    tokens = []
    for call in tool_calls:
        tool_name = call.get("name", "")
        tool_id = TOOL_VOCAB.get(tool_name, UNK)
        status = SUCCESS if call.get("success", True) else FAILURE
        tokens.extend([tool_id, status])

    # Truncate if too long
    if len(tokens) > MAX_SEQ_LEN:
        tokens = tokens[:MAX_SEQ_LEN]

    # Pad to MAX_SEQ_LEN
    tokens = tokens + [PAD] * (MAX_SEQ_LEN - len(tokens))

    return torch.tensor(tokens, dtype=torch.long)


def get_vocab_size() -> int:
    """Return vocab size for tokenizer (100, with room for expansion)."""
    return 100
