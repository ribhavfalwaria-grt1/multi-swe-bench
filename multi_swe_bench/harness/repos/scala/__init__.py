try:
    from multi_swe_bench.harness.repos.scala.scalajs import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.scala.playframework import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.scala.sbt import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.scala.scalanative import *
except (ImportError, ModuleNotFoundError):
    pass
try:
    from multi_swe_bench.harness.repos.scala.scalameta import *
except (ImportError, ModuleNotFoundError):
    pass
