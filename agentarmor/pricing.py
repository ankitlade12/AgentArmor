# Prices in USD per 1,000 tokens
PRICING = {
    # OpenAI
    "gpt-4.5-preview":       {"input": 0.03,    "output": 0.09},
    "gpt-4.5":               {"input": 0.03,    "output": 0.09},
    "o3-mini":               {"input": 0.0011,  "output": 0.0044},
    "gpt-4o":                {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini":           {"input": 0.000150,"output": 0.000600},
    "gpt-4-turbo":           {"input": 0.01,    "output": 0.03},
    "gpt-3.5-turbo":         {"input": 0.0005,  "output": 0.0015},
    # Anthropic
    "claude-4":              {"input": 0.015,   "output": 0.075},
    "claude-opus-4":         {"input": 0.015,   "output": 0.075},
    "claude-sonnet-4-5":     {"input": 0.003,   "output": 0.015},
    "claude-haiku-4-5":      {"input": 0.00025, "output": 0.00125},
    # Google
    "gemini-2.0-pro":        {"input": 0.002,   "output": 0.008},
    "gemini-2.0-flash":      {"input": 0.001,   "output": 0.004},
    "gemini-1.5-pro":        {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash":      {"input": 0.000075,"output": 0.000300},
}

DEFAULT = {"input": 0.01, "output": 0.03}  # Conservative fallback

def get_cost(model: str) -> dict:
    for key in PRICING:
        if key in model.lower():
            return PRICING[key]
    return DEFAULT
