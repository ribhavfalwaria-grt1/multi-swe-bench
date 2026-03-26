try:
    from multi_swe_bench.harness.repos.golang.celestiaorg.celestia_node import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.golang.celestiaorg.celestia_app import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.golang.celestiaorg.go_square import *
except (ImportError, ModuleNotFoundError):
    pass
