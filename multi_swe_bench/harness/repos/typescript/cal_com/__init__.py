import os
from multi_swe_bench.harness.instance import Instance
from .base import CalcomInstance

# Dynamic registration of calcom/cal.com instances
Instance.register("calcom", "cal.com")(CalcomInstance)
