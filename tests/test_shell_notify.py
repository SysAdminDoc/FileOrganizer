"""Tests for fileorganizer.shell_notify — NEXT-67 Windows Explorer notification."""
import sys
import unittest
from unittest.mock import patch, MagicMock

from fileorganizer.shell_notify import notify_shell_moves, notify_shell_single


class TestShellNotify(unittest.TestCase):
    def test_empty_moves_no_error(self):
        notify_shell_moves([])

    def test_single_move_no_error(self):
        notify_shell_single("/src/a.txt", "/dst/a.txt")

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    @patch("fileorganizer.shell_notify.ctypes")
    def test_calls_shchangenotify(self, mock_ctypes):
        mock_shell32 = MagicMock()
        mock_ctypes.windll.shell32 = mock_shell32
        moves = [
            (r"C:\src\file1.txt", r"C:\dst\file1.txt"),
            (r"C:\src\file2.txt", r"C:\dst\file2.txt"),
        ]
        notify_shell_moves(moves)
        self.assertTrue(mock_shell32.SHChangeNotify.called)

    def test_non_windows_graceful(self):
        with patch("fileorganizer.shell_notify._IS_WINDOWS", False):
            notify_shell_moves([("/src/a", "/dst/a")])


if __name__ == "__main__":
    unittest.main()
