import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitCliInstance

# Dynamic registration of tscircuit/cli instances
Instance.register("tscircuit", "cli")(TscircuitCliInstance)
