try:
    from multi_swe_bench.harness.repos.java.apache.dubbo import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.java.apache.maven import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.java.apache.shenyu import *
except (ImportError, ModuleNotFoundError):
    pass
