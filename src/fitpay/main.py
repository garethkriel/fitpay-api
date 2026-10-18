"""Entry point for ASGI servers: `uvicorn fitpay.main:app`, and Vercel.

Vercel loads this file as `src.fitpay.main` (see [tool.vercel] in pyproject.toml) and may not
install the package, so the `src` folder is put on the import path first.
"""

import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent)
if _src not in sys.path:
    sys.path.insert(0, _src)

from fitpay.api.app import create_app  # noqa: E402

app = create_app()
