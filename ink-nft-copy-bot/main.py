#!/usr/bin/env python3
"""Ink Chain Telegram NFT copy-mint bot.

Watches target wallets on Ink (chain id 57073). Copies only free SeaDrop
mintPublic (price=0, window open). Skips signed / allowlist / paid / closed.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.copy_engine import CopyEngine
from src.rpc import RpcPool, WalletStore
from src.telegram_bot import TelegramApp, bind_loop
from src.watcher import MintWatcher

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("ink-nft-copy-bot")


def build(env: str | None = None):
    cfg = load_config(env)
    alert_box: dict = {"fn": lambda t: logger.info("ALERT:\n%s", t)}

    def alert(text: str) -> None:
        alert_box["fn"](text)

    rpc = RpcPool(
        cfg.rpc_urls,
        cfg.chain_id,
        rate_limit=cfg.rpc_rate_limit,
        load_balance=cfg.rpc_load_balance,
        on_alert=alert,
    )
    wallets = WalletStore(cfg.private_keys_env, cfg.mint_wallets_file)
    engine = CopyEngine(
        rpc,
        cfg.seadrop,
        dry_run=cfg.dry_run,
        free_mints_only=cfg.free_mints_only,
        gas_limit=cfg.gas_limit,
        max_fee_gwei=cfg.max_fee_gwei,
        max_priority_fee_gwei=cfg.max_priority_fee_gwei,
        chain_id=cfg.chain_id,
    )
    # placeholder watcher; telegram wires pause
    state = {"paused": cfg.paused}

    watcher = MintWatcher(
        rpc,
        engine,
        wallets,
        seadrop=cfg.seadrop,
        targets=cfg.target_wallets,
        explorer_tx_url=cfg.explorer_tx_url,
        poll_interval=cfg.poll_interval_sec,
        catchup_chunk=cfg.catchup_chunk,
        pending_detection=cfg.pending_detection,
        pending_ws_url=cfg.pending_ws_url,
        state_file=cfg.state_file,
        alert=alert,
        is_paused=lambda: state["paused"],
    )
    tg = TelegramApp(cfg, rpc, wallets, engine, watcher)
    state["paused"] = tg.paused

    def is_paused() -> bool:
        return tg.paused

    watcher.is_paused = is_paused
    alert_box["fn"] = tg.send_alert
    return cfg, rpc, wallets, engine, watcher, tg


def cmd_run(args: argparse.Namespace) -> int:
    cfg, rpc, wallets, engine, watcher, tg = build(args.env)
    logger.info(
        "Starting Ink NFT copy-bot dry_run=%s wallets=%s targets=%s pending=%s",
        cfg.dry_run,
        len(wallets.all()),
        len(watcher.targets),
        cfg.pending_detection,
    )

    app = tg.build_application()

    def watch() -> None:
        try:
            watcher.run_forever()
        except Exception:
            logger.exception("watcher crashed")

    t = threading.Thread(target=watch, name="mint-watcher", daemon=True)
    t.start()

    async def on_start(application) -> None:
        await bind_loop(tg, application)

    app.post_init = on_start
    app.run_polling(drop_pending_updates=True)
    watcher.stop()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg, rpc, wallets, engine, watcher, tg = build(args.env)
    print(tg.online_message())
    print("Tip:", rpc.block_number())
    print("Wallets:", len(wallets.all()))
    print("Targets:", watcher.targets)
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    """Decode a tx and show skip/copy decision without broadcasting (forces dry-run)."""
    cfg, rpc, wallets, engine, watcher, tg = build(args.env)
    engine.dry_run = True
    tx_hash = args.tx if args.tx.startswith("0x") else "0x" + args.tx
    tx = rpc.call("get_transaction", tx_hash)
    if not tx or not tx.get("to"):
        print("TX not found or contract creation")
        return 1
    from src.copy_engine import format_detection, format_results
    from src.seadrop import decode_mint_input
    from src.watcher import ObservedTx
    from web3 import Web3

    raw_in = tx["input"]
    if hasattr(raw_in, "hex"):
        raw_in = raw_in.hex()
    obs = ObservedTx(
        tx_hash=tx_hash,
        from_address=Web3.to_checksum_address(tx["from"]),
        to=Web3.to_checksum_address(tx["to"]),
        value=int(tx["value"]),
        input=raw_in if str(raw_in).startswith("0x") else "0x" + str(raw_in),
        block_number=int(tx["blockNumber"] or 0),
    )
    decoded = decode_mint_input(obs.input, to=obs.to, value=obs.value, seadrop=cfg.seadrop)
    if not decoded:
        print("Not a recognized mint")
        return 1
    outcome = engine.copy(decoded, wallets.all(), their_from=obs.from_address)
    name = engine.collection_name(decoded.nft_contract)
    print(
        format_detection(
            collection_name=name,
            decoded=decoded,
            from_address=obs.from_address,
            block=obs.block_number,
            source_tx=tx_hash,
            explorer_tx_url=cfg.explorer_tx_url,
            hint=decoded.method,
        )
    )
    print()
    print(format_results(outcome, cfg.explorer_tx_url))
    return 0 if outcome.skip_reason or outcome.ok_count else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ink Chain NFT copy-mint Telegram bot")
    p.add_argument("--env", default=None, help="Path to .env")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run watcher + Telegram bot")
    run.set_defaults(func=cmd_run)

    st = sub.add_parser("status", help="Print status without Telegram polling")
    st.set_defaults(func=cmd_status)

    sim = sub.add_parser("simulate", help="Dry-run decide/copy for a tx hash")
    sim.add_argument("tx")
    sim.set_defaults(func=cmd_simulate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())