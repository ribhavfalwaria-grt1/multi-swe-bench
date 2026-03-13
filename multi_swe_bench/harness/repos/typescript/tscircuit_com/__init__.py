import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitComInstance

# Dynamic registration of tscircuit/tscircuit.com instances
Instance.register("tscircuit", "tscircuit.com")(TscircuitComInstance)
