try:
    from multi_swe_bench.harness.repos.golang.open_telemetry.opentelemetry_collector import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.golang.open_telemetry.open_telemetry import *
except (ImportError, ModuleNotFoundError):
    pass
