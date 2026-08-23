"""Ink Chain Telegram NFT copy-mint bot."""

__version__ = "1.0.0"

HONEST_LIMITS = (
    "Cannot forge SeaDrop mintSigned / allowlist proofs.",
    "Short public windows can still close before all wallets land.",
    "Pending detection is faster but riskier (reverts waste gas).",
    "A bad primary RPC fails over to backup; the bot cannot fix a garbled node.",
)