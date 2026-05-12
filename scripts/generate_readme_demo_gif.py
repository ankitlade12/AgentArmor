"""Generate a README demo GIF for AgentArmor.

The GIF is a lightweight terminal-style animation that shows two key product
moments:
1. prompt-injection blocking
2. budget circuit breaking

It intentionally avoids external screen-recording dependencies so the asset can
be regenerated from source with Pillow alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1100
HEIGHT = 720
PADDING_X = 48
PADDING_Y = 54
LINE_HEIGHT = 34
BACKGROUND = "#08111a"
TERMINAL = "#0d1722"
BORDER = "#163246"
TEXT = "#d7e3f4"
MUTED = "#7fa0bc"
ACCENT = "#3ddc97"
WARN = "#ff8a65"
TITLE = "#9ddcff"
OUTPUT = Path("docs/_static/readme-demo.gif")


SCENES = [
    [
        "$ python examples/litellm_example.py",
        "",
        "=== Safe request ===",
        "Runtime safety matters because agents can call tools, spend money,",
        "and move untrusted data across system boundaries in real time.",
        "",
        "=== Blocked request ===",
        "Blocked by AgentArmor: InjectionDetected: prompt injection pattern",
        "matched before the request reached the provider.",
        "",
        "=== Report ===",
        "spent=$0.0031  blocked_requests=1  output_filters=0  budget_left=$1.9969",
    ],
    [
        "$ python examples/crewai_cost_guard_example.py",
        "",
        "AgentArmor + CrewAI Cost Guard Demo",
        "",
        "[crew] step 1 completed: short summary generated",
        "[crew] step 2 starting: detailed checklist requested",
        "",
        "Crew halted by budget guard: BudgetExhausted",
        "The configured budget was reached before the workflow could continue.",
        "",
        "Spent: $0.000500",
        "report: blocked_cost_overrun=1  active_budget_guard=true",
    ],
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/Library/Fonts/Courier New.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


FONT = load_font(25)
FONT_SMALL = load_font(20)


def line_color(line: str) -> str:
    if line.startswith("$ "):
        return ACCENT
    if "Blocked by AgentArmor" in line or "BudgetExhausted" in line:
        return WARN
    if line.startswith("==="):
        return TITLE
    if line.startswith("[crew]") or line.startswith("report:") or line.startswith("spent="):
        return MUTED
    return TEXT


def terminal_frame(lines: Iterable[str], progress: int, scene_index: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    left = 34
    top = 34
    right = WIDTH - 34
    bottom = HEIGHT - 34
    draw.rounded_rectangle((left, top, right, bottom), radius=26, fill=TERMINAL, outline=BORDER, width=2)

    # Window chrome
    chrome_y = top + 20
    for offset, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        x = left + 26 + offset * 22
        draw.ellipse((x, chrome_y, x + 12, chrome_y + 12), fill=color)
    draw.text((left + 92, top + 12), "AgentArmor demo", fill=MUTED, font=FONT_SMALL)

    visible_lines = list(lines)[:progress]
    y = top + PADDING_Y
    for line in visible_lines:
        draw.text((left + PADDING_X, y), line, fill=line_color(line), font=FONT)
        y += LINE_HEIGHT

    footer = "Scene 1: Injection blocking" if scene_index == 0 else "Scene 2: Budget guard"
    draw.text((left + PADDING_X, bottom - 42), footer, fill=MUTED, font=FONT_SMALL)
    return image


def build_frames() -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []

    for scene_index, scene in enumerate(SCENES):
        for progress in range(1, len(scene) + 1):
            frames.append(terminal_frame(scene, progress, scene_index))
            durations.append(220)
        for _ in range(5):
            frames.append(terminal_frame(scene, len(scene), scene_index))
            durations.append(400)
    return frames, durations


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames, durations = build_frames()
    first, rest = frames[0], frames[1:]
    first.save(
        OUTPUT,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=0,
        optimize=False,
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
