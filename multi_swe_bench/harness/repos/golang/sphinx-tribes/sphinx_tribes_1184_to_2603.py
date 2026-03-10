import re
from typing import Optional

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


class ImageDefault(Image):
    """Image for sphinx-tribes late PRs (1184-2603).

    EVIDENCE:
    - PR #1184 CI: go test ./... -tags mock -race -v (FIRST with -tags mock)
    - PR #2603 Dockerfile: FROM golang:1.20.13
    - No go-version specified in CI (uses ubuntu default ~1.20+)

    PRs covered: 1184, 1192, 1216, ... 2603 (106 PRs)
    Date range: 2023-12-24 to 2025-03-02
    """

    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> str:
        # EVIDENCE: PR #2603 Dockerfile uses golang:1.20.13
        return "golang:1.20"

    def image_prefix(self) -> str:
        return "envagent"

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def files(self) -> list[File]:
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
                "prepare.sh",

                """ls -F
###ACTION_DELIMITER###
go mod download
###ACTION_DELIMITER###
go mod tidy
###ACTION_DELIMITER###
go test ./... -tags mock -v -count=1 || true
###ACTION_DELIMITER###
echo "go test ./... -tags mock -race -v -count=1" > test_commands.sh""",
            ),
            File(
                ".",
                "run.sh",

                """#!/bin/bash
cd /home/{pr.repo}
go test ./... -tags mock -race -v -count=1

""".format(pr=self.pr),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
cd /home/{pr.repo}
if ! git -C /home/{pr.repo} apply --whitespace=nowarn /home/test.patch; then
    echo "Error: git apply failed" >&2
    exit 1
fi
go test ./... -tags mock -race -v -count=1

""".format(pr=self.pr),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
cd /home/{pr.repo}
if ! git -C /home/{pr.repo} apply --whitespace=nowarn /home/test.patch /home/fix.patch; then
    echo "Error: git apply failed" >&2
    exit 1
fi
go test ./... -tags mock -race -v -count=1

""".format(pr=self.pr),
            ),
        ]

    def dockerfile(self) -> str:
        copy_commands = ""
        for file in self.files():
            copy_commands += f"COPY {file.name} /home/\n"

        dockerfile_content = """
# Dockerfile for sphinx-tribes late PRs (1184-2603)
# EVIDENCE: PR #2603 Dockerfile uses golang:1.20.13
FROM golang:1.20

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y git

RUN if [ ! -f /bin/bash ]; then         if command -v apk >/dev/null 2>&1; then             apk add --no-cache bash;         elif command -v apt-get >/dev/null 2>&1; then             apt-get update && apt-get install -y bash;         elif command -v yum >/dev/null 2>&1; then             yum install -y bash;         else             exit 1;         fi     fi

WORKDIR /home/
COPY fix.patch /home/
COPY test.patch /home/
RUN git clone https://github.com/stakwork/sphinx-tribes.git /home/sphinx-tribes

WORKDIR /home/sphinx-tribes
RUN git reset --hard
RUN git checkout {pr.base.sha}
"""
        dockerfile_content += f"""
{copy_commands}
"""
        return dockerfile_content.format(pr=self.pr)


@Instance.register("stakwork", "sphinx_tribes_1184_to_2603")
class SPHINX_TRIBES_1184_TO_2603(Instance):
    """Instance for sphinx-tribes late PRs (1184-2603).

    EVIDENCE:
    - PR #1184 CI: go test ./... -tags mock -race -v (FIRST with -tags mock)
    - PR #2603 Dockerfile: FROM golang:1.20.13

    PRs: 1184, 1192, 1216, 1234, ... 2603 (106 PRs)
    Date range: 2023-12-24 to 2025-03-02
    """

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

    def parse_log(self, log: str) -> TestResult:
        """Parse Go test output."""
        passed_tests = set()
        failed_tests = set()
        skipped_tests = set()

        passed_pattern = re.compile(r"--- PASS: (\S+)")
        failed_pattern = re.compile(r"--- FAIL: (\S+)")
        skipped_pattern = re.compile(r"--- SKIP: (\S+)")

        for line in log.splitlines():
            line = line.strip()

            pass_match = passed_pattern.search(line)
            if pass_match:
                test_name = pass_match.group(1)
                if test_name not in failed_tests:
                    passed_tests.add(test_name)
                continue

            fail_match = failed_pattern.search(line)
            if fail_match:
                test_name = fail_match.group(1)
                passed_tests.discard(test_name)
                failed_tests.add(test_name)
                continue

            skip_match = skipped_pattern.search(line)
            if skip_match:
                test_name = skip_match.group(1)
                if test_name not in passed_tests and test_name not in failed_tests:
                    skipped_tests.add(test_name)

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
