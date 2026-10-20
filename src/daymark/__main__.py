"""Allow `py -3 -m daymark`."""

import sys

from daymark.cli import main

if __name__ == "__main__":
    sys.exit(main())
