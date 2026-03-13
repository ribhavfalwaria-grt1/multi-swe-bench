import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitCoreInstance

# Dynamic registration of tscircuit/core instances
Instance.register("tscircuit", "core")(TscircuitCoreInstance)
