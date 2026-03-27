import re
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


def _parse_curl_version(base_label: str) -> tuple[int, int, int]:
    """Parse (major, minor, patch) from base.label like 'curl-7_86_0..curl-7_87_0'."""
    first_tag = base_label.split("..")[0]
    m = re.match(r"curl-(\d+)_(\d+)_(\d+)", first_tag)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"curl-(\d+)_(\d+)", first_tag)
    if m:
        return (int(m.group(1)), int(m.group(2)), 0)
    raise ValueError(f"Cannot parse curl version from base.label: {base_label}")


_VERSION_TO_IMAGE = [
    (8, 0, "ubuntu:24.04"),
    (7, 81, "ubuntu:22.04"),
    (7, 69, "ubuntu:20.04"),
    (7, 59, "ubuntu:18.04"),
]
_DEFAULT_IMAGE = "ubuntu:16.04"


def _get_base_image(version: tuple[int, int, int]) -> str:
    major, minor, _ = version
    for min_major, min_minor, image in _VERSION_TO_IMAGE:
        if major > min_major or (major == min_major and minor >= min_minor):
            return image
    return _DEFAULT_IMAGE


def _use_autoreconf(version: tuple[int, int, int]) -> bool:
    major, minor, _ = version
    if major >= 8:
        return True
    return minor >= 77


class ImageBase(Image):
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
        version = _parse_curl_version(self.pr.base.label)
        return _get_base_image(version)

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
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
RUN apt-get update && \\
    apt-get install -y \\
    build-essential autoconf automake libtool git make gcc g++ \\
    pkg-config perl python3 \\
    libssl-dev libpsl-dev libnghttp2-dev zlib1g-dev \\
    stunnel4 \\
    && apt-get clean

{code}

{self.clear_env}

"""


class ImageDefault(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Image | None:
        return ImageBase(self.pr, self._config)

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def _build_commands(self) -> str:
        version = _parse_curl_version(self.pr.base.label)
        if _use_autoreconf(version):
            return (
                "autoreconf -fi\n"
                "./configure --with-openssl\n"
                "make clean\n"
                "make -j$(nproc)"
            )
        return "./buildconf\n./configure --with-openssl\nmake clean\nmake -j$(nproc)"

    def _test_command(self) -> str:
        return "cd tests && perl runtests.pl -a -p -n"

    def files(self) -> list[File]:
        build_cmds = self._build_commands()
        test_cmd = self._test_command()

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

cd /home/{pr.repo}
git reset --hard
bash /home/check_git_changes.sh
git checkout {pr.base.sha}
bash /home/check_git_changes.sh

""".format(pr=self.pr),
            ),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
set -e

cd /home/{repo}
{build}
{test}
""".format(repo=self.pr.repo, build=build_cmds, test=test_cmd),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
set -e

cd /home/{repo}
git apply --whitespace=nowarn /home/test.patch
{build}
{test}

""".format(repo=self.pr.repo, build=build_cmds, test=test_cmd),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
set -e

cd /home/{repo}
git apply --whitespace=nowarn /home/test.patch /home/fix.patch
{build}
{test}

""".format(repo=self.pr.repo, build=build_cmds, test=test_cmd),
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


@Instance.register("curl", "curl")
class Curl(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return ImageDefault(self.pr, self._config)

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

        # runtests.pl output: "test NNNN..OK", "test NNNN..FAILED", "test NNNN..SKIPPED"
        re_ok = re.compile(r"^test (\d+)\.\.*\s*OK")
        re_fail = re.compile(r"^test (\d+)\.\.*\s*FAILED")
        re_skip = re.compile(r"^test (\d+)\.\.*\s*SKIPPED")

        for line in test_log.splitlines():
            line = line.strip()
            if not line:
                continue

            ok_match = re_ok.match(line)
            if ok_match:
                test_id = ok_match.group(1)
                passed_tests.add(test_id)
                continue

            fail_match = re_fail.match(line)
            if fail_match:
                test_id = fail_match.group(1)
                failed_tests.add(test_id)
                continue

            skip_match = re_skip.match(line)
            if skip_match:
                test_id = skip_match.group(1)
                skipped_tests.add(test_id)

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
