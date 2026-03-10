import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitEvalInstance

# Dynamic registration of tscircuit/eval instances
Instance.register("tscircuit", "eval")(TscircuitEvalInstance)
