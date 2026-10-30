import os
import re

from customizations import util
from customizations.base import Customization, Detection, Status

CURSOR_SHAPE_RE = re.compile(r"^(\s*)cursor_shape\s+(\S+)", re.MULTILINE)
SHELL_RE = re.compile(r"^\s*shell\s+(.+)$", re.MULTILINE)
SHELL_INTEGRATION_RE = re.compile(r"^\s*shell_integration\s+(.+)$", re.MULTILINE)


class KittyBoxCursor(Customization):
    id = "kitty-box-cursor"
    title = "Switch kitty's terminal cursor to a block (box) shape"

    def explain(self, detection: Detection) -> str:
        shape, fish_needs_fix = detection.value
        parts = []
        if shape is not None:
            parts.append(
                f"It appears your kitty cursor_shape is currently set to "
                f"{shape}, not block. kitty's cursor_shape setting controls "
                "the terminal cursor: beam (a thin vertical line), "
                "underline, or block (a solid box). This switches it to "
                f"block, in {util.kitty_user_target()}:\n\n"
                f"{util.indent('cursor_shape block')}"
            )
        if fish_needs_fix:
            parts.append(
                "Note: since you're using fish as kitty's shell, the block "
                "cursor would keep reverting to a beam anyway -- kitty ships "
                'a fish integration script that runs `echo -en "\\e[5 q"` '
                "(set cursor to blinking bar) on every fish_prompt event, "
                "overriding cursor_shape each time you're sitting at a "
                "prompt. This also adds the 'no-cursor' flag to "
                "shell_integration to stop that, leaving the rest of kitty's "
                "shell integration (prompt marking, jump-to-prompt, cwd "
                "tracking) intact:\n\n"
                f"{util.indent('shell_integration no-cursor')}"
            )
        return "\n\n".join(parts)

    # kitty applies directives in load order, so the last one of each wins.
    def _current_shape(self, text: str) -> str | None:
        matches = CURSOR_SHAPE_RE.findall(text)
        return matches[-1][1] if matches else None

    def _shell_integration(self, text: str) -> list[str] | None:
        matches = SHELL_INTEGRATION_RE.findall(text)
        return matches[-1].strip().split() if matches else None

    def _uses_fish(self, text: str) -> bool:
        matches = SHELL_RE.findall(text)
        configured = matches[-1].strip() if matches else None
        if configured and configured != ".":
            return "fish" in configured
        return "fish" in os.environ.get("SHELL", "")

    def _shell_integration_needs_fix(self, text: str) -> bool:
        flags = self._shell_integration(text)
        if flags is None:
            return True  # unset defaults to full integration, cursor forcing included
        return "disabled" not in flags and "no-cursor" not in flags

    def detect(self) -> Detection:
        if util.kitty_user_target() is None:
            return Detection(Status.NOT_APPLICABLE, "no kitty config found (~/.config/kitty/kitty.conf)")
        text = util.kitty_effective_text()

        shape = self._current_shape(text)
        shape_needs_fix = shape not in (None, "block")
        fish_needs_fix = self._uses_fish(text) and self._shell_integration_needs_fix(text)

        if not shape_needs_fix and not fish_needs_fix:
            reason = "cursor_shape is already block" if shape == "block" else "cursor_shape already defaults to block"
            if self._uses_fish(text):
                reason += " and shell_integration already excludes cursor forcing"
            return Detection(Status.ALREADY_APPLIED, reason)

        bits = []
        if shape_needs_fix:
            bits.append(f"cursor_shape is currently {shape}")
        if fish_needs_fix:
            bits.append("fish's shell integration still forces the cursor to a beam on every prompt")
        return Detection(
            Status.APPLICABLE,
            "; ".join(bits),
            value=(shape if shape_needs_fix else None, fish_needs_fix),
        )

    def apply(self) -> str:
        text = util.kitty_effective_text()
        settings = {}
        messages = []

        if self._current_shape(text) not in (None, "block"):
            settings["cursor_shape"] = "block"
            messages.append("set cursor_shape to block")

        if self._uses_fish(text) and self._shell_integration_needs_fix(text):
            flags = self._shell_integration(text) or []
            settings["shell_integration"] = " ".join(flags + ["no-cursor"])
            messages.append("added no-cursor to shell_integration")

        target = util.kitty_set(settings, "freebsd-configurations: block cursor, kept by fish's shell integration")
        return (
            f"In {target}: {', '.join(messages)}. Recent kitty versions "
            "auto-reload their config on save; if yours doesn't, restart "
            "kitty to see the change."
        )


CUSTOMIZATION = KittyBoxCursor()
