try:
    from multi_swe_bench.harness.repos.golang.aws.eks_anywhere import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.golang.aws.eks_distro_build_tooling import *
except (ImportError, ModuleNotFoundError):
    pass
