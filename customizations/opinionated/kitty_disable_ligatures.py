import re

from customizations import util
from customizations.base import Customization, Detection, Status

DISABLE_LIGATURES_RE = re.compile(r"^(\s*)disable_ligatures\s+(\S+)", re.MULTILINE)
FONT_FAMILY_RE = re.compile(r"^\s*font_family\s+(.+)$", re.MULTILINE)


class KittyDisableLigatures(Customization):
    id = "kitty-disable-ligatures"
    title = "Disable kitty's font ligatures"

    def _current_setting(self, text: str) -> str | None:
        # kitty applies directives in load order, so the last one wins.
        matches = DISABLE_LIGATURES_RE.findall(text)
        return matches[-1][1] if matches else None

    def _font_family(self, text: str) -> str | None:
        matches = FONT_FAMILY_RE.findall(text)
        return matches[-1].strip() if matches else None

    def explain(self, detection: Detection) -> str:
        setting, font = detection.value
        current = setting or "never (kitty's default -- ligatures always render)"
        font_note = f" ({font})" if font else ""
        return (
            f"disable_ligatures is currently {current}. Ligatures substitute "
            "a run of characters for a single combined glyph purely for "
            f"display (e.g. '->' becomes an arrow). The substitution happens "
            f"live as you type, and your font{font_note} defines a 3-character "
            "ligature for repeated asterisks (asterisk_asterisk_asterisk.liga, "
            "seemingly meant for Markdown's '***'). Typing a 3rd '*' anywhere "
            "-- a shell glob, a sudo/pwfeedback password prompt echoing "
            "'*' per keystroke, anything -- makes kitty reshape the last "
            "three characters into that combined glyph mid-keystroke, which "
            "visibly nudges the character before it for a frame before it "
            "settles. Confirmed live on this system: 'disable_ligatures "
            "cursor' does NOT fix it (the cursor has already moved past the "
            "ligature's span by the time it forms) -- only 'always' does. "
            f"This sets, in {util.kitty_user_target()}:\n\n"
            f"{util.indent('disable_ligatures always')}\n\n"
            "Trade-off: this turns off ALL ligatures in kitty, not just this "
            "one glyph -- arrows, !=, etc. render as separate characters "
            "everywhere, not just while typing."
        )

    def detect(self) -> Detection:
        if util.kitty_user_target() is None:
            return Detection(Status.NOT_APPLICABLE, "no kitty config found (~/.config/kitty/kitty.conf)")
        text = util.kitty_effective_text()
        setting = self._current_setting(text)

        if setting == "always":
            return Detection(Status.ALREADY_APPLIED, "disable_ligatures is already set to always")

        reason = f"disable_ligatures is currently {setting or 'unset (defaults to never)'}"
        return Detection(Status.APPLICABLE, reason, value=(setting, self._font_family(text)))

    def apply(self) -> str:
        target = util.kitty_set(
            {"disable_ligatures": "always"},
            "freebsd-configurations: stop ligature substitution from jittering repeated glyphs mid-keystroke",
        )
        return (
            f"In {target}: set disable_ligatures to always. Recent "
            "kitty versions auto-reload their config on save; if yours "
            "doesn't, restart kitty to see the change."
        )


CUSTOMIZATION = KittyDisableLigatures()
