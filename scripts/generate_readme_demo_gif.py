"""Generate a README demo GIF for AgentArmor.

The GIF is a lightweight, launch-ready animation that shows three key product
moments:
1. market ecosystem coverage across popular agent libraries
2. prompt-injection blocking
3. budget circuit breaking

It intentionally avoids external screen-recording dependencies so the asset can
be regenerated from source with Pillow alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1200
HEIGHT = 760
PADDING_X = 48
PADDING_Y = 54
LINE_HEIGHT = 34
BACKGROUND = "#08111a"
TERMINAL = "#0d1722"
BORDER = "#163246"
PANEL = "#101d2b"
TEXT = "#d7e3f4"
MUTED = "#7fa0bc"
ACCENT = "#3ddc97"
WARN = "#ff8a65"
TITLE = "#9ddcff"
OK = "#7bd88f"
OUTPUT = Path("docs/_static/readme-demo.gif")


LIBRARIES = [
    ("LiteLLM", "provider router"),
    ("LlamaIndex", "RAG pipelines"),
    ("LangGraph", "multi-step agents"),
    ("CrewAI", "crew workflows"),
    ("Pydantic AI", "typed agents"),
    ("Google ADK", "Gemini agents"),
    ("Agno", "tool-heavy agents"),
    ("MCP", "tool servers"),
]


TERMINAL_SCENES = [
    [
        "$ python examples/langgraph_multistep_example.py",
        "",
        "planner -> writer -> provider",
        "AgentArmor intercepts the provider call before the prompt leaves",
        "the Python process.",
        "",
        "=== Blocked request ===",
        "Blocked by AgentArmor: InjectionDetected",
        "reason=prompt injection pattern matched",
        "provider_call=false",
        "",
        "=== Report ===",
        "blocked_requests=1  trace.closed_reason=blocked  spent=$0.0000",
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


def rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str = BORDER,
    width: int = 2,
    radius: int = 18,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((46, 34), "AgentArmor", fill=TITLE, font=load_font(34))
    draw.text((46, 78), title, fill=TEXT, font=load_font(25))
    draw.text((46, 112), subtitle, fill=MUTED, font=FONT_SMALL)


def ecosystem_frame(progress: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "One local safety layer for the libraries teams already use",
        "No hosted proxy. No framework rewrite. Runtime protection where agents run.",
    )

    hub = (WIDTH // 2 - 190, 330, WIDTH // 2 + 190, 475)

    card_w = 240
    card_h = 94
    positions = [
        (64, 195), (336, 195), (608, 195), (880, 195),
        (64, 510), (336, 510), (608, 510), (880, 510),
    ]
    visible = min(progress, len(LIBRARIES))

    for index, (_, (x, y)) in enumerate(zip(LIBRARIES, positions)):
        if index < visible:
            anchor_y = y + card_h if y < hub[1] else y
            draw.line((x + card_w // 2, anchor_y, WIDTH // 2, hub[1] + 72), fill="#21495f", width=2)

    rounded_box(draw, hub, fill=TERMINAL, outline="#25516a", width=3, radius=24)
    draw.text((hub[0] + 40, hub[1] + 34), "agentarmor.init()", fill=ACCENT, font=load_font(28))
    draw.text((hub[0] + 58, hub[1] + 78), "budget + shield + filter", fill=TEXT, font=FONT_SMALL)
    draw.text((hub[0] + 94, hub[1] + 108), "trace + MCP policy", fill=MUTED, font=FONT_SMALL)

    for index, ((name, detail), (x, y)) in enumerate(zip(LIBRARIES, positions)):
        active = index < visible
        fill = PANEL if active else "#0b1520"
        outline = "#2f6f89" if active else "#142b3c"
        rounded_box(draw, (x, y, x + card_w, y + card_h), fill=fill, outline=outline, radius=18)
        name_color = TEXT if active else "#3b566b"
        detail_color = MUTED if active else "#2d4457"
        draw.text((x + 18, y + 22), name, fill=name_color, font=load_font(22))
        draw.text((x + 18, y + 56), detail, fill=detail_color, font=load_font(16))

    provider_y = 650
    draw.text((48, provider_y), "Patched provider surfaces:", fill=MUTED, font=FONT_SMALL)
    provider_text = "OpenAI Chat + Responses    Anthropic Messages    Google Gemini"
    draw.text((370, provider_y), provider_text, fill=OK, font=FONT_SMALL)
    return image


def terminal_frame(lines: Iterable[str], progress: int, scene_index: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    left = 34
    top = 34
    right = WIDTH - 34
    bottom = HEIGHT - 34
    rounded_box(draw, (left, top, right, bottom), fill=TERMINAL, radius=26)

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

    footer = "Scene 2: Injection blocking" if scene_index == 0 else "Scene 3: Budget guard"
    draw.text((left + PADDING_X, bottom - 42), footer, fill=MUTED, font=FONT_SMALL)
    return image


def build_frames() -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []

    for progress in range(1, len(LIBRARIES) + 1):
        frames.append(ecosystem_frame(progress))
        durations.append(240)
    for _ in range(6):
        frames.append(ecosystem_frame(len(LIBRARIES)))
        durations.append(420)

    for scene_index, scene in enumerate(TERMINAL_SCENES):
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
