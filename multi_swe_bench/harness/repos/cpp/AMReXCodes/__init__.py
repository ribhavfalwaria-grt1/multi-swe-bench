"""AMReX repository handler for Multi-SWE-bench"""
try:
    from .amrex import AMReX
except (ImportError, ModuleNotFoundError):
    pass
