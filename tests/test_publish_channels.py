import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

import publish  # noqa: E402


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class TestHugoChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HUGO_DIR": os.path.join(self.tmp.name, "site")})
        self.env.start()
        os.environ.pop("PUBLISH_REQUIRE_ALL_CHANNELS", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_missing_dir_skipped_locally_failed_in_ci(self):
        self.assertEqual(publish.publish_hugo("x", "2026-11-16", False), publish.SKIPPED)
        with patch.dict(os.environ, {"PUBLISH_REQUIRE_ALL_CHANNELS": "true"}), patch.object(publish, "log_error"):
            self.assertEqual(publish.publish_hugo("x", "2026-11-16", False), publish.FAILED)

    def make_repo(self, push_ok=True):
        remote = os.path.join(self.tmp.name, "remote.git")
        site = os.environ["HUGO_DIR"]
        git("init", "--bare", "-q", remote, cwd=self.tmp.name)
        git("clone", "-q", remote, site, cwd=self.tmp.name)
        git("config", "user.email", "t@example.com", cwd=site)
        git("config", "user.name", "t", cwd=site)
        git("commit", "--allow-empty", "-qm", "init", cwd=site)
        git("push", "-q", "origin", "HEAD", cwd=site)
        if not push_ok:
            git("remote", "set-url", "origin", os.path.join(self.tmp.name, "missing.git"), cwd=site)
        return remote

    def test_push_ok_and_idempotent(self):
        self.make_repo()
        self.assertEqual(publish.publish_hugo("brief", "2026-11-16", False), publish.OK)
        self.assertEqual(publish.publish_hugo("brief", "2026-11-16", False), publish.OK)  # nothing new

    def test_push_failure_reported(self):
        self.make_repo(push_ok=False)
        with patch.object(publish, "log_error"):
            self.assertEqual(publish.publish_hugo("brief", "2026-11-16", False), publish.FAILED)

    def test_dry_run(self):
        os.makedirs(os.environ["HUGO_DIR"])
        self.assertEqual(publish.publish_hugo("brief", "2026-11-16", True), publish.DRY_RUN)


class TestEmailChannel(unittest.TestCase):
    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=False), patch.object(publish, "verify_environment", return_value=False):
            os.environ.pop("PUBLISH_REQUIRE_ALL_CHANNELS", None)
            self.assertEqual(publish.publish_email("b", "d", False), publish.SKIPPED)
            with patch.dict(os.environ, {"PUBLISH_REQUIRE_ALL_CHANNELS": "true"}):
                self.assertEqual(publish.publish_email("b", "d", False), publish.FAILED)

    def test_send_outcomes(self):
        env = {"SMTP_USER": "me@example.com", "SMTP_PASS": "x", "RECIPIENT_EMAIL": ""}
        with patch.dict(os.environ, env):
            with patch.object(publish, "send_email", return_value=True):
                self.assertEqual(publish.publish_email("## 1. MACRO VIEW\n* x", "d", False), publish.OK)
            with patch.object(publish, "send_email", return_value=False), patch.object(publish, "log_error"):
                self.assertEqual(publish.publish_email("b", "d", False), publish.FAILED)


if __name__ == "__main__":
    unittest.main()
