from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from token_quota_widget.instance_lock import InstanceLock


class InstanceLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.name = f"TokenQuotaWidgetTest-{uuid.uuid4().hex}"

    def test_second_instance_is_rejected_and_close_allows_reacquire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = InstanceLock(self.name, runtime_dir=Path(directory))
            try:
                with self.assertRaisesRegex(RuntimeError, "已经在运行"):
                    InstanceLock(self.name, runtime_dir=Path(directory))
            finally:
                first.close()

            replacement = InstanceLock(self.name, runtime_dir=Path(directory))
            replacement.close()

    def test_close_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = InstanceLock(self.name, runtime_dir=Path(directory))
            lock.close()
            lock.close()

    @unittest.skipUnless(os.name == "nt", "Windows import regression")
    def test_ui_imports_without_fcntl(self) -> None:
        import token_quota_widget.ui

        self.assertTrue(callable(token_quota_widget.ui.main))


if __name__ == "__main__":
    unittest.main()
