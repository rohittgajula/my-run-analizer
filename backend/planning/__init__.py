"""Race calendar, mode resolution, finish prediction and plan generation.

Like `analysis`, these modules import no Django. They take plain data and return
plain data, so the whole planning engine is testable without a database.
`tests/test_purity.py` enforces it.
"""
