#!/usr/bin/env python3
"""Robinhood Chain SeaDrop mint copier.

Watches SeaDrop for successful mints. For mintSigned / allowlist stages,
requests a *fresh* OpenSea-signed mint for each of your wallets instead of
replaying the target signature (which is wallet-bound and not copyable).
When a public drop is active, mints via mintPublic directly.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chain import ChainClient
from src.config import load_config
from src.copier import SeaDropCopier, format_copy_report
from src.monitor import MintMonitor
from src.opensea import OpenSeaClient
from src.seadrop import decode_seadrop_input
from src.telegram_notify import TelegramNotifier

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("seadrop-copier")


def build_runtime(config_path: str | None = None):
    cfg = load_config(config_path)
    chain = ChainClient(
        cfg.rpc_url,
        cfg.chain_id,
        max_fee_gwei=cfg.max_fee_gwei,
        max_priority_fee_gwei=cfg.max_priority_fee_gwei,
    )
    opensea = None
    if cfg.opensea_api_key:
        opensea = OpenSeaClient(cfg.opensea_api_key, cfg.opensea_api_base, cfg.opensea_chain)
    else:
        logger.warning(
            "OPENSEA_API_KEY not set — mintSigned / allowlist stages cannot be minted "
            "(will only succeed when public mintPublic is active)"
        )
    copier = SeaDropCopier(
        chain=chain,
        accounts=cfg.accounts,
        seadrop=cfg.seadrop,
        opensea=opensea,
        dry_run=cfg.dry_run,
        default_quantity=cfg.default_quantity,
    )
    notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)
    monitor = MintMonitor(
        chain=chain,
        copier=copier,
        seadrop=cfg.seadrop,
        notifier=notifier,
        explorer_tx_url=cfg.explorer_tx_url,
        poll_seconds=cfg.poll_seconds,
        lookback_blocks=cfg.lookback_blocks,
        state_path=ROOT / "data" / "seen_txs.txt",
        our_addresses=cfg.wallets,
    )
    return cfg, chain, copier, monitor


def cmd_watch(args: argparse.Namespace) -> int:
    cfg, _chain, _copier, monitor = build_runtime(args.env)
    logger.info(
        "Starting watcher dry_run=%s wallets=%s opensea=%s",
        cfg.dry_run,
        len(cfg.accounts),
        bool(cfg.opensea_api_key),
    )
    if args.once:
        reports = monitor.run_once(blocks=args.blocks)
        if not reports:
            print("No SeaDrop mints in lookback window.")
        return 0
    monitor.run_forever()
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    cfg, chain, copier, _monitor = build_runtime(args.env)
    tx_hash = args.tx if args.tx.startswith("0x") else "0x" + args.tx
    tx = chain.w3.eth.get_transaction(tx_hash)
    to = tx["to"]
    if to is None or to.lower() != cfg.seadrop.lower():
        print(f"TX is not a SeaDrop call (to={to})")
        return 1
    raw_input = tx["input"].hex() if hasattr(tx["input"], "hex") else tx["input"]
    decoded = decode_seadrop_input(raw_input)
    if decoded is None:
        print("Could not decode SeaDrop mint input")
        return 1
    print(
        f"Decoded {decoded.method} nft={decoded.nft_contract} qty={decoded.quantity} "
        f"signature_bound={decoded.is_signature_bound}"
    )
    copy = copier.copy_mint(decoded)
    report = format_copy_report(
        decoded,
        copy,
        source_tx=tx_hash,
        from_address=tx["from"],
        block_number=int(tx["blockNumber"] or 0),
        explorer_tx_url=cfg.explorer_tx_url,
        value_wei=int(tx["value"]),
    )
    print(report)
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id).send(report)
    return 0 if copy.ok_count else 2


def cmd_status(args: argparse.Namespace) -> int:
    cfg, chain, _copier, _monitor = build_runtime(args.env)
    tip = chain.get_block_number()
    print(f"RPC: {cfg.rpc_url}")
    print(f"Chain ID: {chain.w3.eth.chain_id} (configured {cfg.chain_id})")
    print(f"Tip block: {tip}")
    print(f"SeaDrop: {cfg.seadrop}")
    print(f"Dry run: {cfg.dry_run}")
    print(f"OpenSea key: {'set' if cfg.opensea_api_key else 'MISSING'}")
    print(f"Wallets ({len(cfg.accounts)}):")
    for acct in cfg.accounts:
        bal = chain.balance(acct.address)
        print(f"  {acct.address}  balance={bal / 1e18:.6f} ETH")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Robinhood SeaDrop mint copier")
    p.add_argument("--env", help="Path to .env file", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    watch = sub.add_parser("watch", help="Watch SeaDrop and copy mints")
    watch.add_argument("--once", action="store_true", help="Scan lookback once and exit")
    watch.add_argument("--blocks", type=int, default=None, help="Lookback blocks for --once")
    watch.set_defaults(func=cmd_watch)

    replay = sub.add_parser("replay", help="Replay / copy a specific SeaDrop tx")
    replay.add_argument("tx", help="Transaction hash")
    replay.set_defaults(func=cmd_replay)

    status = sub.add_parser("status", help="Show config, tip, wallet balances")
    status.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())