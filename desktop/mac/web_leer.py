#!/usr/bin/env python3
"""Lectura web de la lista permitida. No inicia sesión ni envía formularios."""
from __future__ import annotations

import argparse
import sys

from agent_executor import allowed_host, denial, host_of


def juzgar(url: str) -> str:
    if denial({"action": "open_url", "url": url}):
        return "BLOQUEADO"
    if not allowed_host(host_of(url)):
        return "BLOQUEADO"
    return "LEER"


def leer(url: str, *, dry: bool, opener=None) -> str:
    verdict = juzgar(url)
    if verdict != "LEER":
        return verdict
    if dry:
        return "SECO"
    if opener is None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return "FALTA"
        with sync_playwright() as play:
            browser = play.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            title = page.title()
            browser.close()
        return title[:120]
    return opener(url)


def self_test() -> int:
    assert juzgar("https://github.com/x") == "LEER"
    assert juzgar("https://paypal.com/checkout") == "BLOQUEADO"
    assert juzgar("https://example.com/") == "BLOQUEADO"
    assert leer("https://github.com/", dry=True) == "SECO"
    assert leer("https://example.com/", dry=False, opener=lambda url: "no") == "BLOQUEADO"
    print("SELFTEST OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Solo lee URLs de la lista permitida.")
    parser.add_argument("--url", default="")
    parser.add_argument("--leer", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.url:
        print("Falta --url")
        return 2
    result = leer(args.url, dry=not args.leer)
    print(result)
    return 0 if result in {"SECO", "LEER"} or (args.leer and result not in {"BLOQUEADO", "FALTA"}) else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
