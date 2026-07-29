"""Terminal tracing. The fleet's observability surface — and what you screenshot.

Every agent action, bound check, and gate prints here so a grader can read the whole
trajectory without a debugger.
"""

from __future__ import annotations

import os
import sys

_NO_COLOR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()


def _c(code: str) -> str:
    return "" if _NO_COLOR else code


DIM = _c("\033[2m")
BOLD = _c("\033[1m")
RESET = _c("\033[0m")
RED = _c("\033[31m")
GREEN = _c("\033[32m")
YELLOW = _c("\033[33m")
BLUE = _c("\033[34m")
MAGENTA = _c("\033[35m")
CYAN = _c("\033[36m")
GREY = _c("\033[90m")

WIDTH = 78

AGENT_COLOR = {
    "router": CYAN,
    "research": MAGENTA,
    "prd": BLUE,
    "stories": GREEN,
    "validator": YELLOW,
    "executor": RED,
    "fleet": BOLD,
}


def banner(text: str, color: str = BOLD) -> None:
    print(f"\n{color}{'=' * WIDTH}{RESET}")
    for line in text.split("\n"):
        print(f"{color}{line}{RESET}")
    print(f"{color}{'=' * WIDTH}{RESET}")


def rule(text: str = "") -> None:
    if text:
        pad = "-" * max(0, WIDTH - len(text) - 3)
        print(f"{GREY}-- {text} {pad}{RESET}")
    else:
        print(f"{GREY}{'-' * WIDTH}{RESET}")


def agent(name: str, msg: str) -> None:
    color = AGENT_COLOR.get(name, BOLD)
    print(f"{color}[{name:<9}]{RESET} {msg}")


def tool(name: str, tool_name: str, args: dict, result_preview: str = "") -> None:
    color = AGENT_COLOR.get(name, BOLD)
    shown = {k: v for k, v in list(args.items())[:4]}
    print(f"{color}[{name:<9}]{RESET} {DIM}TOOL{RESET} {tool_name}({shown})")
    if result_preview:
        print(f"{' ' * 12}{GREY}-> {result_preview[:190]}{RESET}")


def bound(msg: str, tripped: bool = False) -> None:
    if tripped:
        print(f"{RED}{BOLD}[BOUND     ] TRIPPED — {msg}{RESET}")
    else:
        print(f"{GREY}[bound     ] ok — {msg}{RESET}")


def gate(kind: str, gate_id: str, summary: str) -> None:
    print(f"\n{YELLOW}{BOLD}{'#' * WIDTH}{RESET}")
    print(f"{YELLOW}{BOLD}#  HUMAN GATE — {kind.upper()}   (trust rung: supervised){RESET}")
    print(f"{YELLOW}#  gate id: {gate_id}{RESET}")
    print(f"{YELLOW}#  {summary}{RESET}")
    print(f"{YELLOW}#  Nothing has been created or published. Awaiting approval.{RESET}")
    print(f"{YELLOW}{BOLD}{'#' * WIDTH}{RESET}\n")


def ok(msg: str) -> None:
    print(f"{GREEN}[+] {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[!] {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"{RED}[x] {msg}{RESET}")


def info(msg: str) -> None:
    print(f"{GREY}    {msg}{RESET}")


def artifact(title: str, body: str) -> None:
    print(f"\n{BOLD}+-- {title} {'-' * max(0, WIDTH - len(title) - 5)}{RESET}")
    for line in body.splitlines():
        print(f"{BOLD}|{RESET} {line}")
    print(f"{BOLD}+{'-' * (WIDTH - 1)}{RESET}\n")


def table(headers: list[str], rows: list[list[str]], widths: list[int] | None = None) -> None:
    if not widths:
        widths = [max(len(str(r[i])) for r in [headers] + rows) + 2 for i in range(len(headers))]
    head = "".join(f"{BOLD}{h:<{w}}{RESET}" for h, w in zip(headers, widths))
    print(head)
    print(f"{GREY}{'-' * sum(widths)}{RESET}")
    for row in rows:
        print("".join(f"{str(cell):<{w}}" for cell, w in zip(row, widths)))


def cost(agent_name: str, usd: float, cap: float) -> None:
    pct = (usd / cap * 100) if cap else 0
    color = RED if pct >= 100 else (YELLOW if pct >= 80 else GREY)
    print(f"{color}    cost {agent_name}: ${usd:.4f} / ${cap:.2f} cap ({pct:.0f}%){RESET}")
