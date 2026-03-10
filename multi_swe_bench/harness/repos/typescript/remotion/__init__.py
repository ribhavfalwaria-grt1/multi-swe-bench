import os
from multi_swe_bench.harness.instance import Instance
from .base import RemotionInstance

# Dynamic registration of remotion-dev/remotion instances
Instance.register("remotion-dev", "remotion")(RemotionInstance)
