import re
import shutil
from pathlib import Path

from customizations import util
from customizations.base import Customization, Detection, Status

FASTFETCH_DIR = Path.home() / ".config" / "fastfetch"
CONFIG_JSONC = FASTFETCH_DIR / "config.jsonc"
# Ryoku's ryoku-fastfetch wrapper passes the flags in user.args after
# config.jsonc, which install.sh overwrites on every run; user.args it never
# ships or touches.
USER_ARGS = FASTFETCH_DIR / "user.args"
LOGO_FLAGS = ("--logo", "-l")
HEIGHT_FLAG = "--logo-height"
MARKER = "freebsd-configurations: FreeBSD logo instead of the Ryoku emblem"
RYOKU_EMBLEM = FASTFETCH_DIR / "fastfetch-emblem.png"
SYSTEM_FREEBSD_LOGO = Path("/boot/images/freebsd-logo-rev.png")
LOCAL_FREEBSD_LOGO = FASTFETCH_DIR / "freebsd-logo.png"
LOCAL_FREEBSD_LOGO_SOURCE = "~/.config/fastfetch/freebsd-logo.png"
# The orb is 240x200px. Ryoku's kitty uses JetBrains Mono, whose cells are
# 0.6em wide by 1.32em tall (2.2:1), so at Ryoku's 28-column logo width the
# orb needs 28 / 1.2 / 2.2 ~= 11 rows to keep its proportions (Ryoku's own
# 14 rows, sized for its square emblem, visibly stretches the orb).
LOGO_HEIGHT = 11

_LOGO_KEY_RE = re.compile(r'"logo"\s*:\s*\{')
_SOURCE_RE = re.compile(r'("source"\s*:\s*)"((?:[^"\\]|\\.)*)"')
_HEIGHT_RE = re.compile(r'("height"\s*:\s*)(\d+)')


def _logo_span(text: str) -> tuple[int, int] | None:
    """[start, end) of the top-level "logo" object's body in a JSONC document.

    Ryoku's config.jsonc carries // comments, which json.loads rejects -- and
    round-tripping it through json.dumps would strip them -- so the logo
    object is located and edited as text instead. Strings and comments are
    skipped while matching braces so neither can unbalance the count.
    """
    match = _LOGO_KEY_RE.search(text)
    if match is None:
        return None
    start = match.end()
    depth = 1
    i = start
    while i < len(text):
        c = text[i]
        if c == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            if i == -1:
                return None
        elif text.startswith("/*", i):
            i = text.find("*/", i)
            if i == -1:
                return None
            i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i
        i += 1
    return None


def _logo_field(text: str, regex: re.Pattern) -> str | None:
    span = _logo_span(text)
    if span is None:
        return None
    match = regex.search(text, *span)
    return match.group(2) if match else None


def _set_logo_field(text: str, regex: re.Pattern, value: str) -> str:
    start, end = _logo_span(text)
    match = regex.search(text, start, end)
    return text[:match.start(2)] + value + text[match.end(2):]


def _wrapper_reads_user_args() -> bool:
    wrapper = shutil.which("ryoku-fastfetch")
    try:
        return wrapper is not None and "user.args" in Path(wrapper).read_text(errors="replace")
    except OSError:
        return False


def _user_arg(flags: tuple[str, ...]) -> str | None:
    """The value of the last of `flags` in user.args (the one that wins)."""
    if not USER_ARGS.exists():
        return None
    value = None
    for line in USER_ARGS.read_text().splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in flags:
            value = parts[1].strip()
    return value


def _write_user_args() -> None:
    text = USER_ARGS.read_text() if USER_ARGS.exists() else ""
    if USER_ARGS.exists():
        util.backup(USER_ARGS)
    kept = [
        line for line in text.splitlines()
        if line.strip() != f"# {MARKER}"
        and (line.split() or [""])[0] not in LOGO_FLAGS + (HEIGHT_FLAG,)
    ]
    body = "\n".join(kept).rstrip("\n")
    USER_ARGS.write_text(
        (body + "\n\n" if body else "")
        + f"# {MARKER}\n--logo {LOCAL_FREEBSD_LOGO_SOURCE}\n{HEIGHT_FLAG} {LOGO_HEIGHT}\n"
    )


class RyokuFastfetchFreebsdLogo(Customization):
    id = "ryoku-fastfetch-freebsd-logo"
    title = "Show the FreeBSD logo in fastfetch instead of the Ryoku emblem (Ryoku)"

    def explain(self, detection: Detection) -> str:
        current = detection.value
        return (
            f"It appears fastfetch's logo (~/.config/fastfetch/config.jsonc) is "
            f"currently {current!r}, rather than the FreeBSD logo. Applying "
            f"this copies {SYSTEM_FREEBSD_LOGO} (owned by the base system's "
            f"FreeBSD-bootloader package) to {LOCAL_FREEBSD_LOGO} -- kitty-direct "
            "needs a raster image and a self-contained copy survives the "
            "original moving -- and points logo.source at it, so the fastfetch "
            "greeting shows the FreeBSD orb instead of Ryoku's own emblem. "
            f"logo.height is also set to {LOGO_HEIGHT} so the orb isn't "
            "stretched. "
            + (
                f"Both are written as fastfetch flags to {USER_ARGS}, which "
                "Ryoku's ryoku-fastfetch reads after config.jsonc and never "
                "overwrites, so this survives Ryoku updates. "
                if _wrapper_reads_user_args() else
                "Only those values are rewritten in config.jsonc, so its "
                "comments are kept. "
            )
            + f"The original emblem ({RYOKU_EMBLEM}) is left in place, so "
            "reverting is just pointing the logo back."
        )

    def detect(self) -> Detection:
        if not RYOKU_EMBLEM.exists():
            return Detection(Status.NOT_APPLICABLE, "Ryoku's branded fastfetch is not set up (no fastfetch-emblem.png)")
        if not CONFIG_JSONC.exists():
            return Detection(Status.NOT_APPLICABLE, "no ~/.config/fastfetch/config.jsonc")
        if not SYSTEM_FREEBSD_LOGO.exists():
            return Detection(Status.NOT_APPLICABLE, f"{SYSTEM_FREEBSD_LOGO} is not present on this system")
        try:
            text = CONFIG_JSONC.read_text()
        except OSError:
            text = ""
        current = _logo_field(text, _SOURCE_RE)
        height = _logo_field(text, _HEIGHT_RE)
        if current is None or height is None:
            return Detection(Status.NOT_APPLICABLE, "no logo.source/logo.height found in config.jsonc")
        # flags in user.args win over config.jsonc, when the wrapper reads it.
        if _wrapper_reads_user_args():
            current = _user_arg(LOGO_FLAGS) or current
            height = _user_arg((HEIGHT_FLAG,)) or height
        if (current.removeprefix("file://") == LOCAL_FREEBSD_LOGO_SOURCE and LOCAL_FREEBSD_LOGO.exists()
                and height == str(LOGO_HEIGHT)):
            return Detection(Status.ALREADY_APPLIED, "logo.source is already the FreeBSD logo")
        return Detection(Status.APPLICABLE, f"logo.source is currently {current!r}", value=current)

    def apply(self) -> str:
        # /boot/images files are mode 0444, which copy2 would carry over and
        # then refuse to overwrite on a later re-apply -- so copy bytes only.
        shutil.copyfile(SYSTEM_FREEBSD_LOGO, LOCAL_FREEBSD_LOGO)
        if _wrapper_reads_user_args():
            _write_user_args()
            return f"Copied {SYSTEM_FREEBSD_LOGO} to {LOCAL_FREEBSD_LOGO} and set the logo in {USER_ARGS}."
        util.backup(CONFIG_JSONC)
        text = CONFIG_JSONC.read_text()
        text = _set_logo_field(text, _SOURCE_RE, LOCAL_FREEBSD_LOGO_SOURCE)
        text = _set_logo_field(text, _HEIGHT_RE, str(LOGO_HEIGHT))
        CONFIG_JSONC.write_text(text)
        return f"Copied {SYSTEM_FREEBSD_LOGO} to {LOCAL_FREEBSD_LOGO} and updated {CONFIG_JSONC}."


CUSTOMIZATION = RyokuFastfetchFreebsdLogo()
