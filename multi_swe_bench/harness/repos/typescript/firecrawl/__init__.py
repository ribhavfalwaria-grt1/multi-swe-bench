try:
    import os
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.instance import Instance
except (ImportError, ModuleNotFoundError):
    pass
try:
    from .base import FirecrawlFirecrawlInstance
except (ImportError, ModuleNotFoundError):
    pass

# Dynamic registration of firecrawl/firecrawl instances
Instance.register("firecrawl", "firecrawl")(FirecrawlFirecrawlInstance)
