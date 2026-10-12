"""Access log do helper: 2xx de polling/estático fora do console, resto visível."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from server import coord_tooltip
from server.coord_tooltip import Handler


def _log_request(path: str | None, code: int = 200) -> str:
    """Roda `Handler.log_message` como o http.server faria e devolve a saída."""
    handler = Handler.__new__(Handler)
    if path is not None:
        handler.path = path
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        handler.log_message('"%s" %s %s', f"GET {path} HTTP/1.1", code, "-")
    return buffer.getvalue()


def _log_raw(*args) -> str:
    """Chama `log_message` com argumentos arbitrários (ex.: linhas de log_error)."""
    handler = Handler.__new__(Handler)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        handler.log_message(*args)
    return buffer.getvalue()


class QuietAccessLogTest(unittest.TestCase):
    def test_successful_polls_and_static_files_stay_out_of_the_console(self):
        quiet_paths = (
            "/player-position/state",
            "/player-position/state?verbose=1",
            "/game-marker/state",
            "/mouse-loop/state",
            "/autoloop/status",
            "/arena/status",
            "/health",
            "/ocr-state",
            "/map-tile?z=5&x=1&y=2",
            "/map-icon?src=https%3A%2F%2Fcdn.paldb.cc%2Fx.webp",
            "/assets/index-abc123.js",
            "/assets/ItemCrafterView-IObQ6R0A.css",
            "/breed.json",
            "/index.html",
        )
        for path in quiet_paths:
            with self.subTest(path=path):
                self.assertEqual("", _log_request(path))

    def test_polling_failures_are_still_printed(self):
        for path, code in (
            ("/player-position/state", 500),
            ("/game-marker/state", 403),
            ("/assets/index-abc123.js", 404),
        ):
            with self.subTest(path=path, code=code):
                output = _log_request(path, code)
                self.assertIn(str(code), output)
                self.assertIn(path, output)

    def test_progress_and_page_routes_stay_visible(self):
        self.assertIn("/progress", _log_request("/progress"))
        self.assertIn("/item-crafter", _log_request("/item-crafter"))

    def test_lines_without_a_status_code_are_never_swallowed(self):
        # log_error() do http.server manda só a mensagem, sem código.
        self.assertIn("code 404", _log_raw("%s", "code 404, message File not found"))

    def test_handler_without_path_does_not_swallow_logs(self):
        self.assertIn("200", _log_request(None))

    def test_http_log_all_restores_full_logging(self):
        original = coord_tooltip.HTTP_LOG_ALL
        coord_tooltip.HTTP_LOG_ALL = True
        try:
            self.assertIn("/player-position/state", _log_request("/player-position/state"))
        finally:
            coord_tooltip.HTTP_LOG_ALL = original


if __name__ == "__main__":
    unittest.main()
