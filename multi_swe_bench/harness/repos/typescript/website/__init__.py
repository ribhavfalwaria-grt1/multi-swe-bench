try:
    import os
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.instance import Instance
except (ImportError, ModuleNotFoundError):
    pass
try:
    from .base import ThenewbostonWebsiteInstance
except (ImportError, ModuleNotFoundError):
    pass

# Dynamic registration of thenewboston-blockchain/Website instances
Instance.register("thenewboston-blockchain", "Website")(ThenewbostonWebsiteInstance)
