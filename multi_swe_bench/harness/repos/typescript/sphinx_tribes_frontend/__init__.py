try:
    import os
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.instance import Instance
except (ImportError, ModuleNotFoundError):
    pass
try:
    from .base import StakworkSphinxTribesFrontendInstance
except (ImportError, ModuleNotFoundError):
    pass

# Dynamic registration of stakwork/sphinx-tribes-frontend instances
Instance.register("stakwork", "sphinx-tribes-frontend")(StakworkSphinxTribesFrontendInstance)
