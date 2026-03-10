import os
from multi_swe_bench.harness.instance import Instance
from .base import ArchestraInstance

# Dynamic registration of archestra-ai/archestra instances
Instance.register("archestra-ai", "archestra")(ArchestraInstance)
