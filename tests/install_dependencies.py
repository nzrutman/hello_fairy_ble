"""Install optional dependencies for the selected Home Assistant test version.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import json
import subprocess
import sys
from pathlib import Path

import homeassistant

components = Path(homeassistant.__file__).parent / "components"
requirements = {
    requirement
    for name in ("bluetooth", "usb", "network", "frontend")
    for requirement in json.loads((components / name / "manifest.json").read_text()).get(
        "requirements", []
    )
}
subprocess.check_call([sys.executable, "-m", "pip", "install", *sorted(requirements)])
