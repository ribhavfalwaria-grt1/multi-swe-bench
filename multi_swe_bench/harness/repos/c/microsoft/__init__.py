try:
    from multi_swe_bench.harness.repos.c.microsoft.msquic import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.c.microsoft.xdp_for_windows import *
except (ImportError, ModuleNotFoundError):
    pass
