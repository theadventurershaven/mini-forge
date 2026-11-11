"""Settings and paths.

User settings live in `~/.mini-forge/config.env` (override the folder with MINI_FORGE_HOME).
Environment variables win over the file. Secrets (Meshy key, printer access code) never
leave this file or the environment: do not print or log them.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PACKAGE_DIR = Path(__file__).resolve().parent
OVERLAY_DIR = PACKAGE_DIR / "overlays"


def home_dir() -> Path:
    return Path(os.getenv("MINI_FORGE_HOME") or Path.home() / ".mini-forge")


def config_file() -> Path:
    return home_dir() / "config.env"


def profile_dir() -> Path:
    """Machine and filament profiles generated on this computer by `mini-forge setup`."""
    return home_dir() / "profiles"


if sys.platform == "win32":
    DEFAULT_SLICER = Path(r"C:\Program Files\Bambu Studio\bambu-studio.exe")
elif sys.platform == "darwin":
    DEFAULT_SLICER = Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")
else:
    DEFAULT_SLICER = Path("/usr/bin/bambu-studio")


def system_profile_dir(slicer_path: Path) -> Path:
    """Bambu's bundled BBL profiles: <app>/Contents/Resources/... on macOS, <install>/resources/... elsewhere."""
    mac = slicer_path.parent.parent / "Resources" / "profiles" / "BBL"
    other = slicer_path.parent / "resources" / "profiles" / "BBL"
    return mac if mac.is_dir() else other


# Bed names as the slicer's process setting and as the printer's start command expect them.
BED_TYPES = {
    "textured": ("Textured PEI Plate", "textured_plate"),
    "smooth": ("High Temp Plate", "hot_plate"),
    "engineering": ("Engineering Plate", "eng_plate"),
    "cool": ("Cool Plate", "cool_plate"),
}

# Minimum feature size used by the mesh check, by nozzle. A thin warning is a review prompt,
# not a reason to thicken the sculpt.
FEATURE_FLOOR_MM = {0.2: 0.3, 0.4: 1.2}


@dataclass(frozen=True)
class Settings:
    slicer_path: Path
    printer_model: str            # Bambu system name without the nozzle, e.g. "Bambu Lab P1S"
    nozzle: float                 # nozzle installed right now
    bed: str                      # key of BED_TYPES
    filament: str                 # Bambu system filament profile, e.g. "Bambu PLA Basic @BBL X1C"
    meshy_api_key: str | None
    printer_host: str | None      # optional: Bambu LAN printing
    printer_serial: str | None
    printer_access_code: str | None
    ams_slot: int                 # 1-4; 0 means the external spool holder
    downloads_pickup: bool = False  # optional, off unless the user turns it on (`mini-forge downloads-pickup on`)
    downloads_dir: Path | None = None

    @classmethod
    def load(cls) -> Settings:
        values = {**{k: v for k, v in dotenv_values(config_file()).items() if v is not None}, **os.environ}
        get = lambda k, d=None: (values.get(k) or d)
        return cls(
            slicer_path=Path(get("SLICER_PATH") or DEFAULT_SLICER),
            printer_model=get("PRINTER_MODEL", "Bambu Lab P1S"),
            nozzle=float(get("NOZZLE", "0.4")),
            bed=get("BED", "textured"),
            filament=get("FILAMENT", "Bambu PLA Basic @BBL X1C"),
            meshy_api_key=get("MESHY_API_KEY"),
            printer_host=get("PRINTER_HOST"),
            printer_serial=get("PRINTER_SERIAL"),
            printer_access_code=get("PRINTER_ACCESS_CODE"),
            ams_slot=int(get("AMS_SLOT", "1")),
            downloads_pickup=str(get("DOWNLOADS_PICKUP", "off")).lower() == "on",
            downloads_dir=Path(get("DOWNLOADS_DIR") or Path.home() / "Downloads"),
        )

    def printer_configured(self) -> bool:
        return bool(self.printer_host and self.printer_serial and self.printer_access_code)

    def secrets(self) -> list[str]:
        return [s for s in (self.meshy_api_key, self.printer_host, self.printer_serial, self.printer_access_code) if s]

    def redact(self, text: str) -> str:
        for s in self.secrets():
            text = text.replace(s, "[redacted]")
        return text


def review_font(size: int):
    """A TrueType font for review renders, falling back to PIL's default."""
    from PIL import ImageFont
    for path in ("/System/Library/Fonts/Helvetica.ttc", r"C:\Windows\Fonts\arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)
