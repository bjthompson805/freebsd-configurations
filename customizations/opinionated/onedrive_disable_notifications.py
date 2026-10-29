import os
import re
import shutil
import subprocess
from pathlib import Path

from customizations import util
from customizations.base import Customization, Detection, Status

CONFIG_DIR = Path.home() / ".config" / "onedrive"
CONFIG_PATH = CONFIG_DIR / "config"
KEY = "disable_notifications"
LINE = f'{KEY} = "true"'
MARKER = "freebsd-configurations: silence onedrive monitor notifications"

# onedrive's config is `key = "value"` lines; `#` starts a comment.
_KEY_RE = re.compile(r'^[ \t]*' + KEY + r'[ \t]*=[ \t]*"([^"]*)"[ \t]*$', re.MULTILINE)


def _monitor_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-U", str(os.getuid()), "-f", "onedrive.*(--monitor|-m)"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


class OnedriveDisableNotifications(Customization):
    id = "onedrive-disable-notifications"
    title = "Silence desktop notifications from the OneDrive monitor"

    def detect(self) -> Detection:
        if shutil.which("onedrive") is None:
            return Detection(Status.NOT_APPLICABLE, "onedrive is not installed")
        if not CONFIG_DIR.is_dir():
            return Detection(
                Status.NOT_APPLICABLE,
                "onedrive hasn't been set up yet (no ~/.config/onedrive)",
            )
        text = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else ""
        match = _KEY_RE.search(text)
        if match is not None and match.group(1).lower() == "true":
            return Detection(Status.ALREADY_APPLIED, f'{KEY} is already "true" in {CONFIG_PATH}')
        current = f'"{match.group(1)}"' if match else "unset (defaults to false)"
        return Detection(Status.APPLICABLE, f"{KEY} is {current}", value=current)

    def explain(self, detection: Detection) -> str:
        return (
            f"It appears {KEY} is currently {detection.value} in {CONFIG_PATH}.\n\n"
            "In monitor mode the onedrive client raises a desktop notification "
            "for sync events -- files uploaded/downloaded, conflicts, errors -- "
            "every time they happen in the background. Setting this turns "
            "those off so the monitor syncs silently:\n\n"
            f"  {LINE}\n\n"
            "This goes in onedrive's own config file rather than on its command "
            "line, so it takes effect however onedrive is launched here (a "
            "Hyprland autostart, an rc script, a terminal) -- there's no "
            "systemd unit on FreeBSD to drop an override into.\n\n"
            "Trade-off: you stop getting a toast when a sync fails (expired "
            "auth, a full disk, a file conflict) -- you'd need to check "
            "onedrive's own output or log to notice."
        )

    def apply(self) -> str:
        text = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else ""
        if _KEY_RE.search(text):
            util.backup(CONFIG_PATH)
            CONFIG_PATH.write_text(_KEY_RE.sub(LINE, text, count=1))
        else:
            util.append_block(CONFIG_PATH, LINE, MARKER)

        message = f"Set {LINE} in {CONFIG_PATH}."
        if _monitor_running():
            message += (
                " A running `onedrive --monitor` was found -- restart it to "
                "pick this up (it only reads its config at startup)."
            )
        return message


CUSTOMIZATION = OnedriveDisableNotifications()
