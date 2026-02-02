# competition/run_all.py

import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import threading
import queue

LOG = logging.getLogger("competition-runner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

HERE = Path(__file__).resolve().parent

# Preferred order first, then any new scrapers get appended automatically
PREFERRED_ORDER = ["boosterpakker", "hatamontcg", "laboge", "lcg_cards", "pokemadness"]

# Anything in this set will NOT be treated as a scraper
EXCLUDE = {
    "__init__",
    "run_all",
    # helpers / libs
    "normalize",
    "canonicalize",
    "pipeline",
    "pricing",
    "scrape_utils",
    "cardcenter"
}

DEFAULT_TIMEOUT_SECONDS = 20 * 60  # 20 minutes per scraper


def now_oslo() -> str:
    return datetime.now(ZoneInfo("Europe/Oslo")).isoformat()


def detect_chrome_bin() -> str | None:
    # What worked for you earlier
    candidate = "/snap/chromium/current/usr/lib/chromium-browser/chrom"
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return None


def _enqueue_output(pipe, q: queue.Queue[str]):
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            q.put(line.rstrip("\n"))
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def looks_like_scraper(py_path: Path) -> bool:
    """
    Quick heuristic to avoid running helper modules by accident.
    - Must define a main-ish entrypoint.
    - Must import selenium driver or create_chromium_driver.
    (Keeps it simple and robust across your scrapers.)
    """
    try:
        txt = py_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False

    if "if __name__ == \"__main__\"" not in txt:
        return False

    # most of your scrapers use this
    if "create_chromium_driver" in txt:
        return True

    # fallback: selenium usage
    if "selenium" in txt and "WebDriverWait" in txt:
        return True

    return False


def list_scrapers() -> list[Path]:
    files: list[Path] = []
    for p in HERE.glob("*.py"):
        if p.stem in EXCLUDE:
            continue

        # prevent helpers from being executed if someone forgets to add to EXCLUDE
        if not looks_like_scraper(p):
            continue

        files.append(p)

    # sort by preferred order, then alphabetically
    by_name = {p.stem: p for p in files}
    ordered: list[Path] = []

    for name in PREFERRED_ORDER:
        if name in by_name:
            ordered.append(by_name.pop(name))

    for name in sorted(by_name.keys()):
        ordered.append(by_name[name])

    return ordered


def run_scraper(path: Path, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> int:
    start = time.time()
    name = path.stem

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if not env.get("CHROME_BIN"):
        chrome_bin = detect_chrome_bin()
        if chrome_bin:
            env["CHROME_BIN"] = chrome_bin

    LOG.info("[%s] ▶ start (%s)", name, str(path))

    proc = subprocess.Popen(
        [sys.executable, "-u", str(path)],
        cwd=str(HERE.parent),  # project root (same as before)
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    q: queue.Queue[str] = queue.Queue()
    assert proc.stdout is not None
    t = threading.Thread(target=_enqueue_output, args=(proc.stdout, q), daemon=True)
    t.start()

    try:
        while True:
            # stream logs while waiting, enforcing timeout
            try:
                line = q.get(timeout=0.2)
                if line:
                    LOG.info("[%s] %s", name, line)
            except queue.Empty:
                pass

            rc = proc.poll()
            if rc is not None:
                break

            if (time.time() - start) > timeout_seconds:
                raise subprocess.TimeoutExpired(proc.args, timeout_seconds)

        elapsed = time.time() - start
        if rc == 0:
            LOG.info("[%s] ✅ ok in %.1fs", name, elapsed)
        else:
            LOG.error("[%s] ❌ rc=%s in %.1fs", name, rc, elapsed)
        return int(rc or 0)

    except subprocess.TimeoutExpired:
        LOG.error("[%s] ⏱️ timeout after %ss — killing", name, timeout_seconds)
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return 124

    except KeyboardInterrupt:
        LOG.warning("[%s] interrupted — terminating child", name)
        try:
            proc.terminate()
        except Exception:
            pass
        raise


def main():
    LOG.info("🏁 Competition runner starting at %s", now_oslo())

    scrapers = list_scrapers()
    if not scrapers:
        LOG.error("No scraper files detected in %s", str(HERE))
        sys.exit(2)

    LOG.info("Will run scrapers in this order: %s", ", ".join([p.stem for p in scrapers]))

    overall_rc = 0
    for p in scrapers:
        rc = run_scraper(p)
        if rc != 0 and overall_rc == 0:
            overall_rc = rc

        # tiny gap between runs
        time.sleep(1)

    sys.exit(overall_rc)


if __name__ == "__main__":
    main()
