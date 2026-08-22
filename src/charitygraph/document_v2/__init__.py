"""Private, cache-aware document syntax extraction; never a public-card writer."""
from .pipeline import extract_document
from .evaluate import run_benchmark
__all__=["extract_document","run_benchmark"]
