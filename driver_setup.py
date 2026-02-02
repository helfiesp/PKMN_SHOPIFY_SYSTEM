"""Shared Selenium driver setup for competition scrapers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService


def create_chromium_driver(
    headless: bool = True,
    use_old_headless: bool = False,
    window_size: str = "1280,720",
    user_agent: Optional[str] = None,
):
    options = webdriver.ChromeOptions()

    chrome_binary = os.getenv("CHROME_BINARY")
    if not chrome_binary:
        common_paths = [
            r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
        ]
        for path in common_paths:
            if path and Path(path).exists():
                chrome_binary = path
                break
    if chrome_binary and Path(chrome_binary).exists():
        options.binary_location = chrome_binary

    if headless:
        options.add_argument("--headless" if use_old_headless else "--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={window_size}")
    
    # Suppress common Chrome warnings/errors
    options.add_argument("--log-level=3")  # Suppress console logs (fatal only)
    options.add_argument("--silent")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-features=ChromeWhatsNewUI")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-usb-keyboard-detect")  # Suppress USB errors
    options.add_experimental_option('excludeSwitches', ['enable-logging'])  # Suppress DevTools logs
    
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")

    # 1) Prefer explicit chromedriver path if provided
    driver_path = os.getenv("CHROMEDRIVER_PATH")
    if driver_path and Path(driver_path).exists():
        service = ChromeService(driver_path)
        try:
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(60)
            return driver
        except Exception as e:
            raise RuntimeError(
                f"ChromeDriver failed to start. This usually means a version mismatch between Chrome and ChromeDriver. "
                f"Chrome version: Check chrome://version/. ChromeDriver path: {driver_path}. Error: {str(e)}"
            )

    # 2) Try Selenium Manager (bundled with selenium >= 4.6)
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        return driver
    except Exception:
        pass

    raise RuntimeError(
        "Unable to start Chrome driver. Ensure Chrome is installed or set CHROME_BINARY to chrome.exe. "
        "Optionally set CHROMEDRIVER_PATH to a local chromedriver.exe. Selenium Manager requires internet access."
    )
