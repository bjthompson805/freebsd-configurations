import re
import shutil
from pathlib import Path

from customizations import util
from customizations.base import Customization, Detection, Status

MIMEAPPS = Path.home() / ".config" / "mimeapps.list"
APPLICATION_DIRS = [
    Path.home() / ".local" / "share" / "applications",
    Path("/usr/local/share/applications"),
]
# (CLI, desktop id) pairs, in order of preference. There's no `vscode` package
# in pkg, so which one exists depends on how VS Code got onto this box:
# Microsoft's build under Linux compat or a manual install provides `code`,
# the editors/vscode port builds Code - OSS as `code-oss`, and VSCodium is
# `codium`.
VSCODE_CANDIDATES = [
    ("code", "code.desktop"),
    ("code-oss", "code-oss.desktop"),
    ("codium", "codium.desktop"),
]
SECTION = "[Default Applications]"
SECTION_RE = re.compile(r"^\[.*\]\s*$", re.MULTILINE)

# Ryoku ships all of these pointed at ryoku-nvim.desktop. text/markdown and
# text/html are deliberately left out -- those are commonly pointed at a
# dedicated markdown viewer or a browser rather than a code editor, and
# clobbering a user's own override there isn't this customization's business.
TEXT_MIMETYPES = [
    "text/plain",
    "application/json",
    "text/xml",
    "application/xml",
    "text/x-shellscript",
    "application/x-shellscript",
    "text/x-python",
    "text/x-lua",
    "text/css",
    "text/x-csrc",
    "text/x-chdr",
    "text/x-c++src",
    "text/x-go",
    "application/toml",
    "text/x-toml",
    "application/x-yaml",
    "text/yaml",
]

FISH_MARKER = "freebsd-configurations: VS Code as EDITOR/VISUAL"
FISH_BLOCK = "set -gx EDITOR code-wait\nset -gx VISUAL code-wait"

WRAPPER = Path.home() / ".local" / "bin" / "code-wait"


def _find_vscode() -> tuple[str, str] | None:
    """The first installed (CLI, desktop id) pair, or None if VS Code isn't installed."""
    for cli, desktop_id in VSCODE_CANDIDATES:
        if shutil.which(cli) is None:
            continue
        if any((d / desktop_id).exists() for d in APPLICATION_DIRS):
            return cli, desktop_id
    return None


def _wrapper_content(cli: str) -> str:
    return f'#!/bin/sh\nexec {cli} --wait "$@"\n'


def _pending(cli: str, desktop_id: str, fish_target: Path) -> tuple[bool, bool, dict[str, str]]:
    """(shell_missing, wrapper_missing, wrong mimetypes) for the current on-disk state."""
    fish_text = fish_target.read_text() if fish_target.exists() else ""
    shell_missing = FISH_MARKER not in fish_text
    wrapper_missing = not (WRAPPER.exists() and WRAPPER.read_text() == _wrapper_content(cli))
    current = _current_mapping(MIMEAPPS.read_text()) if MIMEAPPS.exists() else {}
    wrong = {m: current.get(m, "(unset)") for m in TEXT_MIMETYPES if current.get(m) != desktop_id}
    return shell_missing, wrapper_missing, wrong


def _current_mapping(text: str) -> dict[str, str]:
    """Parse `key=value` lines that fall within the [Default Applications] section."""
    lines = text.splitlines()
    section_starts = [i for i, line in enumerate(lines) if SECTION_RE.match(line)]
    start = next((i for i in section_starts if lines[i].strip() == SECTION), None)
    if start is None:
        return {}
    end = next((i for i in section_starts if i > start), len(lines))

    mapping = {}
    for line in lines[start + 1:end]:
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        mapping[key.strip()] = value.strip()
    return mapping


def _set_mapping(text: str, updates: dict[str, str]) -> str:
    lines = text.splitlines()
    section_starts = [i for i, line in enumerate(lines) if SECTION_RE.match(line)]
    start = next((i for i in section_starts if lines[i].strip() == SECTION), None)

    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(SECTION)
        for mimetype, desktop_id in updates.items():
            lines.append(f"{mimetype}={desktop_id}")
        return "\n".join(lines) + "\n"

    end = next((i for i in section_starts if i > start), len(lines))
    remaining = dict(updates)
    for i in range(start + 1, end):
        line = lines[i]
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"

    insert_at = end
    for mimetype, desktop_id in remaining.items():
        lines.insert(insert_at, f"{mimetype}={desktop_id}")
        insert_at += 1

    return "\n".join(lines) + "\n"


class VscodeDefaultEditor(Customization):
    id = "vscode-default-editor"
    title = "Make VS Code the default text/code editor (instead of neovim)"

    def detect(self) -> Detection:
        found = _find_vscode()
        if found is None:
            clis = ", ".join(f"`{cli}`" for cli, _ in VSCODE_CANDIDATES)
            return Detection(
                Status.NOT_APPLICABLE,
                f"VS Code is not installed (none of {clis} on PATH with a "
                "matching .desktop entry)",
            )
        cli, desktop_id = found

        fish_target = util.fish_user_target()
        if fish_target is None:
            return Detection(Status.NOT_APPLICABLE, "no fish config found (~/.config/fish)")

        shell_missing, wrapper_missing, wrong = _pending(cli, desktop_id, fish_target)
        if not shell_missing and not wrapper_missing and not wrong:
            return Detection(Status.ALREADY_APPLIED, f"EDITOR/VISUAL and the text mimetypes already point at {cli}")

        reason_bits = []
        if shell_missing or wrapper_missing:
            reason_bits.append(f"EDITOR/VISUAL aren't pointed at {cli}")
        if wrong:
            reason_bits.append(f"{len(wrong)} text mimetype(s) aren't mapped to {desktop_id}")
        return Detection(
            Status.APPLICABLE,
            ", ".join(reason_bits),
            value=(cli, desktop_id, shell_missing, wrapper_missing, wrong, fish_target),
        )

    def explain(self, detection: Detection) -> str:
        cli, desktop_id, shell_missing, wrapper_missing, wrong, fish_target = detection.value
        parts = [
            "Ryoku defaults both the shell's $EDITOR/$VISUAL and the "
            "desktop's file-open mimetype map to neovim (ryoku-nvim.desktop). "
            f"This switches both to VS Code (found as `{cli}`) instead."
        ]
        if shell_missing or wrapper_missing:
            parts.append(
                f"Writes {WRAPPER}:\n\n"
                f"{util.indent(_wrapper_content(cli).rstrip())}\n\n"
                "and, in "
                f"{fish_target}, appends (so it wins over ryoku's own "
                f"`set -gx EDITOR nvim` earlier in the file, without editing "
                f"ryoku's lines in place):\n\n"
                f"{util.indent(FISH_BLOCK)}\n\n"
                "$EDITOR/$VISUAL point at the wrapper rather than the literal "
                f"string \"{cli} --wait\": several consumers of these variables "
                "(git and other shell-based tools) re-split the value on "
                "whitespace themselves, but not all do -- anything that "
                "spawns $EDITOR directly as a single executable (e.g. a TUI's "
                "own click-to-open-in-editor handler) will fail to find a "
                f"binary literally named \"{cli} --wait\" and silently no-op. "
                "The wrapper keeps $EDITOR a single token for every consumer, "
                "while still adding VS Code's `--wait` flag so callers that "
                "block on the editor exiting (git commit, crontab -e, "
                "sudoedit) work correctly."
            )
        if wrong:
            sample = ", ".join(f"{k} -> {v}" for k, v in list(wrong.items())[:5])
            more = f" (+{len(wrong) - 5} more)" if len(wrong) > 5 else ""
            parts.append(
                f"In {MIMEAPPS}, remaps {len(wrong)} text/code mimetype(s) "
                f"currently not pointed at {desktop_id}: {sample}{more}. "
                "text/markdown and text/html are deliberately left alone -- "
                "those are commonly pointed at a markdown viewer or a "
                "browser instead, and this customization only owns the "
                "code-editor mimetypes."
            )
        return "\n\n".join(parts)

    def apply(self) -> str:
        # Re-detect fresh state rather than trusting a possibly-stale Detection.
        cli, desktop_id = _find_vscode()
        fish_target = util.fish_user_target()
        shell_missing, wrapper_missing, wrong = _pending(cli, desktop_id, fish_target)

        results = []
        if wrapper_missing:
            WRAPPER.parent.mkdir(parents=True, exist_ok=True)
            if WRAPPER.exists():
                util.backup(WRAPPER)
            WRAPPER.write_text(_wrapper_content(cli))
            WRAPPER.chmod(0o755)
            results.append(f"wrote {WRAPPER}")

        if shell_missing:
            util.append_block(fish_target, FISH_BLOCK, FISH_MARKER)
            results.append(f"exported EDITOR/VISUAL as code-wait in {fish_target}")

        if wrong:
            updates = {m: desktop_id for m in wrong}
            if MIMEAPPS.exists():
                util.backup(MIMEAPPS)
                text = MIMEAPPS.read_text()
            else:
                text = f"{SECTION}\n"
            MIMEAPPS.write_text(_set_mapping(text, updates))
            results.append(f"mapped {len(updates)} text mimetype(s) to {desktop_id} in {MIMEAPPS}")

        return "; ".join(results).capitalize() + ". Open a new shell to pick up EDITOR/VISUAL."


CUSTOMIZATION = VscodeDefaultEditor()
