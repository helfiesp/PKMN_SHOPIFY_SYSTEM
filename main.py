#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

SHOPIFY_FETCH = SCRIPT_DIR / "shopify_fetch_collection.py"
SNKRDUNK = SCRIPT_DIR / "snkrdunk.py"
UPDATER = SCRIPT_DIR / "shopify_price_updater_confirmed.py"
STOCK_REPORT = SCRIPT_DIR / "shopify_stock_report.py"
BOOSTER_VARIANTS = SCRIPT_DIR / "shopify_booster_variants.py"
BOOSTER_INVENTORY = SCRIPT_DIR / "shopify_booster_inventory_split.py"

DATA_DIR = SCRIPT_DIR / "data"
SHOPIFY_DIR = SCRIPT_DIR / "shopify"
LAST_BOOSTER_PLAN_MARKER = DATA_DIR / "last_booster_price_plan_path.txt"

# Booster collection rules
BOOSTER_COLLECTION_ID = "444116140283"
BOOSTER_EXCLUDES = "one piece,deluxe"


def die(msg: str, code: int = 1) -> None:
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    raise SystemExit(code)


def run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print("\n" + "=" * 90)
    print("RUN:", " ".join(cmd))
    print("=" * 90 + "\n")
    proc = subprocess.run(cmd, cwd=str(SCRIPT_DIR), env=env)
    return int(proc.returncode)


def require_files() -> None:
    for p in (SHOPIFY_FETCH, SNKRDUNK, UPDATER, STOCK_REPORT, BOOSTER_VARIANTS, BOOSTER_INVENTORY):
        if not p.exists():
            die(f"Missing required script: {p.name}")


def show_menu() -> None:
    print("=== Price pipeline main ===")
    print("1) Full pipeline: Shopify snapshot -> SNKRDUNK -> Generate plan (no updates)")
    print("2) Step 1 only: Fetch Shopify snapshot")
    print("3) Step 2 only: Run SNKRDUNK (requires Shopify snapshot)")
    print("4) Step 3a only: Generate plan (no updates)")
    print("5) Step 3b: Apply an existing price plan (requires CONFIRM)")
    print("6) Generate Shopify stock report (supplier JSON)")
    print("7) Booster variants: Generate plan (no changes)")
    print("8) Booster variants: Apply plan (requires CONFIRM)")
    print("9) Booster inventory split: Generate plan (no changes)")
    print("10) Booster inventory split: Apply plan (requires CONFIRM)")
    print("11) FULL BOOSTER PRICE PIPELINE (NO APPLY): fetch boosters -> SNKRDUNK -> plan (box + derived pack)")
    print("12) APPLY BOOSTER PRICE PLAN (no rerun): apply last generated booster plan (box + derived pack)")
    print("13) Exit")


def prompt(msg: str) -> str:
    return input(msg).strip()


def ensure_env_key(name: str) -> None:
    if not os.getenv(name, "").strip():
        die(f"Missing environment variable: {name}")


def latest_snapshot_for_collection(collection_id: str) -> Path:
    return SHOPIFY_DIR / f"collection_{collection_id}_active_variants.json"

def latest_plan_file(prefix: str = "price_update_plan_") -> Path | None:
    """Return newest plan file in DATA_DIR matching prefix, based on mtime."""
    if not DATA_DIR.exists():
        return None
    candidates = sorted(DATA_DIR.glob(f"{prefix}*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None



def pipeline_plan_only(env: dict[str, str], snapshot: Path) -> int:
    # Step 1: Fetch Shopify snapshot
    rc = run_cmd([sys.executable, str(SHOPIFY_FETCH)], env=env)
    if rc != 0:
        print("Step 1 failed.")
        return rc

    # Step 2: SNKRDUNK on the snapshot
    snkr_env = env.copy()
    snkr_env["SHOPIFY_SNAPSHOT_FILE"] = str(snapshot)
    rc = run_cmd([sys.executable, str(SNKRDUNK)], env=snkr_env)
    if rc != 0:
        print("Step 2 failed.")
        return rc

    # Step 3a: Generate plan (no apply)
    up_env = env.copy()
    up_env["SHOPIFY_SNAPSHOT_FILE"] = str(snapshot)
    rc = run_cmd([sys.executable, str(UPDATER)], env=up_env)
    if rc != 0:
        print("Step 3a failed.")
        return rc

    return 0


def main() -> int:
    require_files()

    while True:
        show_menu()
        choice = prompt("\nChoose: ")

        if choice == "13" or choice.lower() in {"q", "quit", "exit"}:
            print("Bye.")
            return 0

        valid = {"1","2","3","4","5","6","7","8","9","10","11","12"}
        if choice not in valid:
            print("Invalid choice.")
            continue

        # Base env checks
        if choice in {"1", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12"}:
            ensure_env_key("SHOPIFY_TOKEN")
            ensure_env_key("SHOPIFY_SHOP")
        if choice in {"1", "3", "11", "12"}:
            ensure_env_key("GOOGLE_TRANSLATE_API_KEY")

        # 1) Full pipeline (plan only) for whatever the default collection is
        if choice == "1":
            # Uses whatever TARGET_COLLECTION_NUMERIC_ID is (or the fetch script default)
            env = os.environ.copy()
            rc = run_cmd([sys.executable, str(SHOPIFY_FETCH)], env=env)
            if rc != 0:
                print("Step 1 failed.")
                continue

            # Let SNKRDUNK / UPDATER use their own defaults unless explicitly overridden
            rc = run_cmd([sys.executable, str(SNKRDUNK)], env=env)
            if rc != 0:
                print("Step 2 failed.")
                continue

            rc = run_cmd([sys.executable, str(UPDATER)], env=env)
            print(f"Done (exit code {rc}).")
            continue

        # 2) Fetch Shopify snapshot
        if choice == "2":
            rc = run_cmd([sys.executable, str(SHOPIFY_FETCH)], env=os.environ.copy())
            print(f"Done (exit code {rc}).")
            continue

        # 3) Run SNKRDUNK
        if choice == "3":
            rc = run_cmd([sys.executable, str(SNKRDUNK)], env=os.environ.copy())
            print(f"Done (exit code {rc}).")
            continue

        # 4) Generate plan (no updates)
        if choice == "4":
            rc = run_cmd([sys.executable, str(UPDATER)], env=os.environ.copy())
            print(f"Done (exit code {rc}).")
            continue

        # 5) Apply an existing price plan
        if choice == "5":
            latest = DATA_DIR / "price_update_plan_latest.json"
            print("\nApply mode requires a plan file.")
            if latest.exists():
                print(f"Latest plan detected: {latest}")

            plan_path_str = prompt("Plan file path (press Enter to use latest): ")
            if not plan_path_str:
                if not latest.exists():
                    print("No plan files found in ./data.")
                    continue
                plan_path = latest
            else:
                plan_path = Path(plan_path_str).expanduser().resolve()
                if not plan_path.exists():
                    print(f"Plan not found: {plan_path}")
                    continue

            print("\nYou are about to APPLY price updates to Shopify.")
            print("This will only update price + compareAtPrice, and only if live prices match the plan snapshot.")
            confirm = prompt("Type APPLY to continue: ")
            if confirm != "APPLY":
                print("Cancelled.")
                continue

            env = os.environ.copy()
            env["APPLY_CHANGES"] = "1"
            env["CONFIRM_PLAN"] = str(plan_path)

            rc = run_cmd([sys.executable, str(UPDATER)], env=env)
            print(f"Done (exit code {rc}).")
            continue

        # 6) Stock report
        if choice == "6":
            rc = run_cmd([sys.executable, str(STOCK_REPORT)], env=os.environ.copy())
            print(f"Done (exit code {rc}).")
            continue

        # 7) Booster variants plan
        if choice == "7":
            env = os.environ.copy()
            env.pop("APPLY_CHANGES", None)
            env.pop("CONFIRM_PLAN", None)
            rc = run_cmd([sys.executable, str(BOOSTER_VARIANTS)], env=env)
            print(f"Done (exit code {rc}).")
            continue

        # 8) Booster variants apply (latest)
        if choice == "8":
            latest = DATA_DIR / "booster_variant_plan_latest.json"
            if not latest.exists():
                print("No latest variant plan found. Run plan first (menu 7).")
                continue

            print("\nYou are about to APPLY booster-variant changes to Shopify.")
            print("This will create/ensure a Booster Pack variant and rename option to Type.")
            print("Safety: it only applies if current title + box price match the plan.")
            confirm = prompt("Type APPLY to continue: ")
            if confirm != "APPLY":
                print("Cancelled.")
                continue

            env = os.environ.copy()
            env["APPLY_CHANGES"] = "1"
            env["CONFIRM_PLAN"] = str(latest)

            rc = run_cmd([sys.executable, str(BOOSTER_VARIANTS)], env=env)
            print(f"Done (exit code {rc}).")
            continue

        # 9) Booster inventory split plan
        if choice == "9":
            env = os.environ.copy()
            env.pop("APPLY_CHANGES", None)
            env.pop("CONFIRM_PLAN", None)
            rc = run_cmd([sys.executable, str(BOOSTER_INVENTORY)], env=env)
            print(f"Done (exit code {rc}).")
            continue

        # 10) Booster inventory split apply (latest)
        if choice == "10":
            latest = DATA_DIR / "booster_inventory_plan_latest.json"
            if not latest.exists():
                print("No latest inventory plan found. Run plan first (menu 9).")
                continue

            print("\nYou are about to APPLY booster inventory split changes to Shopify.")
            print("This will move 1 Booster Box into Booster Packs (packs_per_box) for products where box stock > 1.")
            confirm = prompt("Type APPLY to continue: ")
            if confirm != "APPLY":
                print("Cancelled.")
                continue

            env = os.environ.copy()
            env["APPLY_CHANGES"] = "1"
            env["CONFIRM_PLAN"] = str(latest)

            rc = run_cmd([sys.executable, str(BOOSTER_INVENTORY)], env=env)
            print(f"Done (exit code {rc}).")
            continue

        # 11) Full booster pricing pipeline (plan only; box + derived pack)
        if choice == "11":
            print("\nRunning FULL BOOSTER PRICE PIPELINE (NO APPLY).")
            print(f"Collection: {BOOSTER_COLLECTION_ID} (excluding: {BOOSTER_EXCLUDES})")
            print("Result: Generates a price plan where Booster Box is priced from SNKRDUNK and Booster Pack is derived.\n")

            env = os.environ.copy()
            env["TARGET_COLLECTION_NUMERIC_ID"] = BOOSTER_COLLECTION_ID
            env["EXCLUDE_TITLE_CONTAINS"] = BOOSTER_EXCLUDES

            snapshot = latest_snapshot_for_collection(BOOSTER_COLLECTION_ID)

            rc = pipeline_plan_only(env, snapshot)
            if rc == 0:
                plan_path = latest_plan_file(prefix="price_update_plan_")
                if plan_path:
                    try:
                        LAST_BOOSTER_PLAN_MARKER.write_text(str(plan_path), encoding="utf-8")
                        print(f"Latest booster plan recorded: {plan_path}")
                    except Exception:
                        pass
            print(f"Done (exit code {rc}).")
            continue


        # 12) Apply booster price plan (no rerun)
        if choice == "12":
            # Prefer the last plan recorded by option 11; fallback to newest plan file.
            plan_path = None
            if LAST_BOOSTER_PLAN_MARKER.exists():
                try:
                    p = Path(LAST_BOOSTER_PLAN_MARKER.read_text(encoding="utf-8").strip())
                    if p.exists():
                        plan_path = p
                except Exception:
                    plan_path = None

            if not plan_path:
                plan_path = latest_plan_file(prefix="price_update_plan_")

            if not plan_path or not plan_path.exists():
                print("No booster price plan found to apply. Run option 11 first to generate a plan.")
                continue

            print("\nBooster price plan ready to apply:")
            print(f"  {plan_path}")
            print("\nVerify the JSON file contents now. When you are ready, come back and apply.")
            confirm = prompt("Type APPLY to apply this plan, or press Enter to cancel: ")
            if confirm != "APPLY":
                print("Cancelled.")
                continue

            env = os.environ.copy()
            # Enforce booster collection rules (aligns apply context with how plan was produced)
            env["TARGET_COLLECTION_NUMERIC_ID"] = BOOSTER_COLLECTION_ID
            env["EXCLUDE_TITLE_CONTAINS"] = BOOSTER_EXCLUDES

            env["APPLY_CHANGES"] = "1"
            env["CONFIRM_PLAN"] = str(plan_path)

            rc = run_cmd([sys.executable, str(UPDATER)], env=env)
            print(f"Done (exit code {rc}).")
            continue

            env = os.environ.copy()
            env["TARGET_COLLECTION_NUMERIC_ID"] = BOOSTER_COLLECTION_ID
            env["EXCLUDE_TITLE_CONTAINS"] = BOOSTER_EXCLUDES

            snapshot = latest_snapshot_for_collection(BOOSTER_COLLECTION_ID)

            rc = pipeline_plan_only(env, snapshot)
            if rc != 0:
                print(f"Pipeline failed (exit code {rc}).")
                continue

            plan_path = latest_plan_file(prefix="price_update_plan_")
            if not plan_path:
                print("Could not find a generated plan file in ./data (price_update_plan_*.json).")
                continue

            apply_env = env.copy()
            apply_env["APPLY_CHANGES"] = "1"
            apply_env["CONFIRM_PLAN"] = str(plan_path)
            # Ensure updater uses the booster snapshot explicitly
            apply_env["SHOPIFY_SNAPSHOT_FILE"] = str(snapshot)

            rc = run_cmd([sys.executable, str(UPDATER)], env=apply_env)
            print(f"Done (exit code {rc}).")
            continue


if __name__ == "__main__":
    raise SystemExit(main())
