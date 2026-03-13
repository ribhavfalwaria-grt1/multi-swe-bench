import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitFootprinterInstance

# Dynamic registration of tscircuit/footprinter instances
Instance.register("tscircuit", "footprinter")(TscircuitFootprinterInstance)
