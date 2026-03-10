import os
from multi_swe_bench.harness.instance import Instance
from .base import TscircuitJscadElectronicsInstance

# Dynamic registration of tscircuit/jscad-electronics instances
Instance.register("tscircuit", "jscad-electronics")(TscircuitJscadElectronicsInstance)
