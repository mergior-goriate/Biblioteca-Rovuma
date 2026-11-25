from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import Mock, patch

from .remote_processor import ProcessorServer, job_directory, process, run_job


class PrivateTransportTests(TestCase):
    def test_isolated_worker_result_and_cleanup(self):
        with TemporaryDirectory() as root:
            with job_directory(Path(root)) as folder:
                (folder / "result.json").write_text('{"pages": 1}', encoding="utf-8")
                self.assertEqual(run_job(folder, Path(root)), {"pages": 1})
            self.assertFalse(folder.exists())

    def test_remote_origin_uses_https(self):
        key = "temporary-local-test-key-" * 2
        with TemporaryDirectory() as root:
            source = Path(root) / "original"
            source.write_bytes(b"ensaio")
            response = Mock(status=200)
            response.getheader.side_effect = {
                "X-PDF-Pages": "1",
                "X-Original-SHA256": sha256(b"ensaio").hexdigest(),
                "Content-Length": "0",
            }.get
            with patch("documents.remote_processor.http.client.HTTPSConnection") as https:
                https.return_value.getresponse.return_value = response
                result = process("https://processor.example.invalid", key, source, "pdf", source)
                https.assert_called_once_with("processor.example.invalid", 443, timeout=850)
                method, route, _, headers = https.return_value.request.call_args.args
                self.assertEqual((method, route), ("POST", "/process"))
                self.assertEqual(headers["Authorization"], f"Bearer {key}")
                self.assertEqual(result["pages"], 1)

    def test_rejects_insecure_external_origin(self):
        key = "temporary-local-test-key-" * 2
        for url in ("http://processor.example.invalid", "ftp://worker.railway.internal",
                    "https://user@processor.example.invalid", "https://processor.example.invalid/other"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                process(url, key, None, "pdf", None)

    def test_authorization_and_converted_formats_round_trip(self):
        key = "temporary-local-test-key-" * 2
        payload = b"Conteudo de ensaio"
        converted = b"%PDF-1.7"
        with ProcessorServer(("::1", 0), key) as server, TemporaryDirectory() as root:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port, *_ = server.server_address
                def worker(folder, required):
                    self.assertTrue(required)
                    self.assertEqual((folder / "original").read_bytes(), payload)
                    (folder / "reader.pdf").write_bytes(converted)
                    return {"pages": 3, "sha256": sha256(payload).hexdigest()}

                with closing(HTTPConnection(host, port, timeout=5)) as connection:
                    connection.request("POST", "/process", b"", {"X-Document-Format": "docx"})
                    self.assertEqual(connection.getresponse().status, 401)

                source = Path(root) / "original"
                target = Path(root) / "reader.pdf"
                source.write_bytes(payload)
                with patch("documents.remote_processor.signatures_ready", return_value=True), \
                     patch("documents.remote_processor.run_one", side_effect=worker), \
                     patch("documents.remote_processor.http.client.HTTPConnection",
                           side_effect=lambda name, port, timeout: HTTPConnection(host, port, timeout=5)):
                    for file_format in ("docx", "odt", "txt"):
                        with self.subTest(file_format=file_format):
                            result = process(f"http://processador.railway.internal:{port}", key, source, file_format, target)
                            self.assertEqual(result["pages"], 3)
                            self.assertEqual(target.read_bytes(), converted)
                            # The client can finish reading before the handler releases the slot.
                            self.assertTrue(server.slot.acquire(timeout=5))
                            server.slot.release()
            finally:
                server.shutdown()
                thread.join()
