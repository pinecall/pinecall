"""`python -m pinecall.serve`: what the one CLI runs."""

import sys

from pinecall.serve import main

sys.exit(main(sys.argv[1:]))
