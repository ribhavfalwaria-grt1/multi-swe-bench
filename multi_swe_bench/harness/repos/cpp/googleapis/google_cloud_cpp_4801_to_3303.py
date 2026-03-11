import re
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest

_VALID_COMPONENTS = frozenset(
    {
        "storage",
        "bigtable",
    }
)


def _detect_components_era1(test_patch: str, fix_patch: str) -> set[str]:
    components = set()
    for patch in (test_patch, fix_patch):
        for line in patch.split("\n"):
            if line.startswith("diff --git"):
                filepath = line.split(" b/")[-1]
                parts = filepath.split("/")
                if len(parts) >= 3 and parts[0] == "google" and parts[1] == "cloud":
                    comp = parts[2]
                    if comp in _VALID_COMPONENTS:
                        components.add(comp)
    if not components:
        return {"storage", "bigtable"}
    return components


class Era1ImageBase(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Union[str, "Image"]:
        return "ubuntu:18.04"

    def image_tag(self) -> str:
        return "base"

    def workdir(self) -> str:
        return "base"

    def files(self) -> list[File]:
        return []

    def dockerfile(self) -> str:
        image_name = self.dependency()
        if isinstance(image_name, Image):
            image_name = image_name.image_full_name()

        if self.config.need_clone:
            code = f"RUN git clone https://github.com/{self.pr.org}/{self.pr.repo}.git /home/{self.pr.repo}"
        else:
            code = f"COPY {self.pr.repo} /home/{self.pr.repo}"

        return f"""FROM {image_name}

{self.global_env}

WORKDIR /home/
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \\
    build-essential cmake git ninja-build \\
    patch pkg-config tar wget curl zip unzip \\
    libcurl4-openssl-dev libssl-dev zlib1g-dev \\
    ca-certificates automake autoconf libtool \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/google/crc32c/archive/1.0.6.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=yes \\
      -DCRC32C_BUILD_TESTS=OFF -DCRC32C_BUILD_BENCHMARKS=OFF -DCRC32C_USE_GLOG=OFF \\
      -GNinja -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && cd /var/tmp && rm -fr build

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/protocolbuffers/protobuf/archive/v3.9.1.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=yes \\
      -Dprotobuf_BUILD_TESTS=OFF \\
      -GNinja -S cmake -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && cd /var/tmp && rm -fr build

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/c-ares/c-ares/archive/cares-1_14_0.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=yes \\
      -GNinja -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ./buildconf && ./configure && \\
    install -m 644 -D -t /usr/local/lib/pkgconfig libcares.pc && \\
    ldconfig && cd /var/tmp && rm -fr build

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/grpc/grpc/archive/v1.24.3.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \\
      -DgRPC_INSTALL=ON -DgRPC_BUILD_TESTS=OFF \\
      -DgRPC_CARES_PROVIDER=package \\
      -DgRPC_PROTOBUF_PROVIDER=package \\
      -DgRPC_SSL_PROVIDER=package \\
      -DgRPC_ZLIB_PROVIDER=package \\
      -GNinja -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && cd /var/tmp && rm -fr build

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/googleapis/cpp-cmakefiles/archive/v0.1.5.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=yes \\
      -GNinja -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && cd /var/tmp && rm -fr build

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/google/googletest/archive/release-1.10.0.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=yes \\
      -GNinja -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && cd /var/tmp && rm -fr build

WORKDIR /var/tmp/build
RUN curl -sSL https://github.com/googleapis/google-cloud-cpp-common/archive/v0.16.0.tar.gz | \\
    tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=yes \\
      -DBUILD_TESTING=OFF \\
      -DGOOGLE_CLOUD_CPP_TESTING_UTIL_ENABLE_INSTALL=ON \\
      -GNinja -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && cd /var/tmp && rm -fr build

RUN ldconfig /usr/local/lib*

WORKDIR /home/

{code}

{self.clear_env}

"""


class Era1ImageDefault(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Image:
        return Era1ImageBase(self.pr, self._config)

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def files(self) -> list[File]:
        components = _detect_components_era1(self.pr.test_patch, self.pr.fix_patch)

        enable_bigtable = "ON" if "bigtable" in components else "OFF"
        enable_storage = "ON" if "storage" in components else "OFF"

        return [
            File(
                ".",
                "fix.patch",
                f"{self.pr.fix_patch}",
            ),
            File(
                ".",
                "test.patch",
                f"{self.pr.test_patch}",
            ),
            File(
                ".",
                "check_git_changes.sh",
                """#!/bin/bash
set -e

if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  echo "check_git_changes: Not inside a git repository"
  exit 1
fi

if [[ -n $(git status --porcelain) ]]; then
  echo "check_git_changes: Uncommitted changes"
  exit 1
fi

echo "check_git_changes: No uncommitted changes"
exit 0

""",
            ),
            File(
                ".",
                "prepare.sh",
                """#!/bin/bash
set -e

cd /home/{repo}
git reset --hard
bash /home/check_git_changes.sh
git checkout {base_sha}
bash /home/check_git_changes.sh

mkdir -p build && cd build
cmake -S /home/{repo} -B /home/{repo}/build \\
    -DBUILD_TESTING=ON \\
    -DGOOGLE_CLOUD_CPP_ENABLE_BIGTABLE={enable_bigtable} \\
    -DGOOGLE_CLOUD_CPP_ENABLE_STORAGE={enable_storage} \\
    -DGOOGLE_CLOUD_CPP_ENABLE_FIRESTORE=OFF \\
    -DCMAKE_BUILD_TYPE=Debug \\
    -GNinja
cmake --build /home/{repo}/build -j $(nproc)

""".format(
                    repo=self.pr.repo,
                    base_sha=self.pr.base.sha,
                    enable_bigtable=enable_bigtable,
                    enable_storage=enable_storage,
                ),
            ),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
set -e

cd /home/{repo}/build
ctest --output-on-failure

""".format(repo=self.pr.repo),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
set -e

cd /home/{repo}
git apply --whitespace=nowarn /home/test.patch
cd build
cmake --build . -j $(nproc)
ctest --output-on-failure

""".format(repo=self.pr.repo),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
set -e

cd /home/{repo}
git apply --whitespace=nowarn /home/test.patch /home/fix.patch
cd build
cmake --build . -j $(nproc)
ctest --output-on-failure

""".format(repo=self.pr.repo),
            ),
        ]

    def dockerfile(self) -> str:
        image = self.dependency()
        name = image.image_name()
        tag = image.image_tag()

        copy_commands = ""
        for file in self.files():
            copy_commands += f"COPY {file.name} /home/\n"

        prepare_commands = "RUN bash /home/prepare.sh"

        return f"""FROM {name}:{tag}

{self.global_env}

{copy_commands}

{prepare_commands}

{self.clear_env}

"""


@Instance.register("googleapis", "google-cloud-cpp_4801_to_3303")
class GoogleCloudCpp4801To3303(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return Era1ImageDefault(self.pr, self._config)

    def run(self, run_cmd: str = "") -> str:
        if run_cmd:
            return run_cmd

        return "bash /home/run.sh"

    def test_patch_run(self, test_patch_run_cmd: str = "") -> str:
        if test_patch_run_cmd:
            return test_patch_run_cmd

        return "bash /home/test-run.sh"

    def fix_patch_run(self, fix_patch_run_cmd: str = "") -> str:
        if fix_patch_run_cmd:
            return fix_patch_run_cmd

        return "bash /home/fix-run.sh"

    def parse_log(self, test_log: str) -> TestResult:
        passed_tests = set()
        failed_tests = set()
        skipped_tests = set()

        re_pass_tests = [
            re.compile(r"^\d+/\d+\s*Test\s*#\d+:\s*(.*?)\s*\.+\s*Passed"),
        ]
        re_fail_tests = [
            re.compile(r"^\d+/\d+\s*Test\s*#\d+:\s*(.*?)\s*\.+\s*\*+Failed"),
            re.compile(r"^\d+/\d+\s*Test\s*#\d+:\s*(.*?)\s*\.+\s*\*+Timeout"),
        ]
        re_skip_tests = [
            re.compile(r"^\d+/\d+\s*Test\s*#\d+:\s*(.*?)\s*\.+\s*\*+Not Run"),
        ]

        for line in test_log.splitlines():
            line = line.strip()
            if not line:
                continue

            for re_pass in re_pass_tests:
                pass_match = re_pass.match(line)
                if pass_match:
                    test = pass_match.group(1)
                    passed_tests.add(test)

            for re_fail in re_fail_tests:
                fail_match = re_fail.match(line)
                if fail_match:
                    test = fail_match.group(1)
                    failed_tests.add(test)

            for re_skip in re_skip_tests:
                skip_match = re_skip.match(line)
                if skip_match:
                    test = skip_match.group(1)
                    skipped_tests.add(test)

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
