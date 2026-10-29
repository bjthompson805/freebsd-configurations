import json
import shutil
import subprocess
from pathlib import Path

from customizations import util
from customizations.base import Customization, Detection, Status

BRAND_JSON = Path.home() / ".config" / "ryoku" / "brand.json"
FREEBSD_LOGO = Path("/boot/images/freebsd-logo-rev.png")
# The shipped PNG has transparent padding around the orb, and Ryoku fits the
# whole image into the mark's box, so a trimmed copy renders noticeably larger.
TRIMMED_LOGO = BRAND_JSON.parent / "freebsd-logo-trimmed.png"


class RyokuBrandFreebsdLogo(Customization):
    id = "ryoku-brand-freebsd-logo"
    title = "Use the FreeBSD logo as the Ryoku brand mark (Ryoku)"

    def explain(self, detection: Detection) -> str:
        current = detection.value
        state = f"set to {current!r}" if current else "using the default 力 text mark"
        return (
            f"It appears Ryoku's brand mark (~/.config/ryoku/brand.json) is currently "
            f"{state}, rather than the FreeBSD logo shipped at {FREEBSD_LOGO} (owned by "
            "the base system's FreeBSD-bootloader package, which draws it in the boot "
            "menu). Applying this sets markImage to that file, so the pill, launcher, "
            "and other branded surfaces show the FreeBSD orb instead of Ryoku's own "
            "mark. The logo's transparent padding is trimmed (into "
            f"{TRIMMED_LOGO}) so the orb fills the mark's space.\n\n"
            "markTint is also turned off: with it on (Ryoku's default) the orb is "
            "recoloured to your theme's accent instead of FreeBSD red.\n\n"
            "Note: if Ryoku Settings (Super + ,) is open, save or close it before "
            "applying this -- it rewrites related files on save and could overwrite "
            "this change."
        )

    def _load(self) -> dict:
        return json.loads(BRAND_JSON.read_text())

    def detect(self) -> Detection:
        if not BRAND_JSON.exists():
            return Detection(Status.NOT_APPLICABLE, "Ryoku is not installed (no ~/.config/ryoku/brand.json)")
        if not FREEBSD_LOGO.exists():
            return Detection(Status.NOT_APPLICABLE, f"{FREEBSD_LOGO} is not present on this system")
        if not shutil.which("magick"):
            return Detection(Status.NOT_APPLICABLE, "ImageMagick (magick) is not installed")
        try:
            data = self._load()
        except (json.JSONDecodeError, OSError):
            return Detection(Status.NOT_APPLICABLE, "brand.json could not be parsed")
        current = data.get("markImage", "")
        if current.removeprefix("file://") == str(TRIMMED_LOGO) and TRIMMED_LOGO.exists() and data.get("markTint") is False:
            return Detection(Status.ALREADY_APPLIED, "markImage is already the FreeBSD logo")
        return Detection(Status.APPLICABLE, f"markImage is currently {current!r}", value=current)

    def apply(self) -> str:
        util.backup(BRAND_JSON)
        data = self._load()
        subprocess.run(["magick", str(FREEBSD_LOGO), "-trim", "+repage", str(TRIMMED_LOGO)], check=True)
        data["markImage"] = str(TRIMMED_LOGO)
        data["markTint"] = False
        BRAND_JSON.write_text(json.dumps(data, indent=4) + "\n")
        return f"Updated {BRAND_JSON} to use {TRIMMED_LOGO} (trimmed from {FREEBSD_LOGO})."


CUSTOMIZATION = RyokuBrandFreebsdLogo()
