import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitCircuitToSvgInstance

# Dynamic registration of tscircuit/circuit-to-svg instances
Instance.register("tscircuit", "circuit-to-svg")(TscircuitCircuitToSvgInstance)
