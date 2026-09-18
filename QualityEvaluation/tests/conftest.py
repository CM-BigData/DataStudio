import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]  # Project root used to locate the src source directory.
SRC_ROOT = PROJECT_ROOT / "src"  # src package directory used for direct local imports in tests.
if str(SRC_ROOT) not in sys.path:  # Add src explicitly when the package is not installed in the test environment.
    sys.path.insert(0, str(SRC_ROOT))
