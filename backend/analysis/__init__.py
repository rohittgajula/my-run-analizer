"""Pure calculators: segmentation, run/walk truth, pace, heart rate, load.

**Nothing in this package may import Django.** Functions take plain data and return
plain data. That is what lets the metrics engine be tested without a database, which
is where most of this project's tests live — `tests/test_purity.py` enforces it in a
subprocess, so the guard is a test rather than a convention.
"""
