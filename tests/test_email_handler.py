import logging
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

import logger
from logger import EmailHandler, load_email_config


class FakeSMTP:
    """Records the emails instead of sending them."""
    sent = []
    fail = False
    lock = threading.Lock()

    def __init__(self, server, port, timeout=None):
        self.server = server
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.user = user
        self.password = password

    def send_message(self, message):
        if FakeSMTP.fail:
            raise OSError("connection refused")
        with FakeSMTP.lock:
            FakeSMTP.sent.append(message)


def make_record(message, level=logging.CRITICAL, name="app.test"):
    return logging.LogRecord(name, level, __file__, 0, message, None, None)


def wait_for(condition, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class EmailHandlerTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.sent = []
        FakeSMTP.fail = False
        patcher = mock.patch.object(logger.smtplib, "SMTP", FakeSMTP)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_handler(self, min_interval=60):
        handler = EmailHandler("smtp.example.com", 587, "sender@example.com", "secret",
                               ["a@example.com", "b@example.com"], min_interval=min_interval)
        handler.setLevel(logging.CRITICAL)
        return handler

    def test_critical_record_is_emailed_to_all_recipients(self):
        handler = self.make_handler()
        handler.handle(make_record("GAS ALARM 1 ACTIVATED"))
        self.assertTrue(wait_for(lambda: len(FakeSMTP.sent) == 1))
        handler.close()

        message = FakeSMTP.sent[0]
        self.assertEqual(message["To"], "a@example.com, b@example.com")
        self.assertEqual(message["From"], "sender@example.com")
        self.assertIn("CRITICAL app.test: GAS ALARM 1 ACTIVATED", message["Subject"])
        self.assertIn("GAS ALARM 1 ACTIVATED", message.get_content())

    def test_lower_levels_are_not_emailed(self):
        handler = self.make_handler(min_interval=0)
        test_logger = logging.getLogger("app.test_email_levels")
        test_logger.setLevel(logging.DEBUG)
        test_logger.propagate = False
        test_logger.addHandler(handler) # the logger is what filters by the handler level
        self.addCleanup(test_logger.removeHandler, handler)

        test_logger.warning("device unreachable")
        test_logger.error("read failed")
        test_logger.critical("GAS ALARM")
        handler.close()
        self.assertEqual(len(FakeSMTP.sent), 1)
        self.assertIn("GAS ALARM", FakeSMTP.sent[0]["Subject"])

    def test_burst_within_min_interval_is_one_email(self):
        handler = self.make_handler(min_interval=0.5)
        handler.handle(make_record("first"))
        self.assertTrue(wait_for(lambda: len(FakeSMTP.sent) == 1))
        for text in ("second", "third"):
            handler.handle(make_record(text))
        time.sleep(0.2) # still within min_interval: nothing new sent yet
        self.assertEqual(len(FakeSMTP.sent), 1)
        self.assertTrue(wait_for(lambda: len(FakeSMTP.sent) == 2))
        handler.close()

        batched = FakeSMTP.sent[1]
        self.assertIn("(and 1 more)", batched["Subject"])
        self.assertIn("second", batched.get_content())
        self.assertIn("third", batched.get_content())

    def test_smtp_error_is_printed_and_handler_keeps_working(self):
        handler = self.make_handler(min_interval=0)
        FakeSMTP.fail = True
        with mock.patch("builtins.print") as printed:
            handler.handle(make_record("lost"))
            self.assertTrue(wait_for(lambda: printed.called))
        self.assertIn("Error sending email", printed.call_args[0][0])

        FakeSMTP.fail = False
        handler.handle(make_record("delivered"))
        self.assertTrue(wait_for(lambda: len(FakeSMTP.sent) == 1))
        handler.close()

    def test_close_flushes_pending_records(self):
        handler = self.make_handler(min_interval=60)
        handler.handle(make_record("first"))
        self.assertTrue(wait_for(lambda: len(FakeSMTP.sent) == 1))
        handler.handle(make_record("pending")) # would wait 60 s for the next email
        handler.close()

        self.assertFalse(handler.worker.is_alive())
        self.assertEqual(len(FakeSMTP.sent), 2)
        self.assertIn("pending", FakeSMTP.sent[1].get_content())


class LoadEmailConfigTests(unittest.TestCase):
    def write_config(self, text):
        handle, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(handle, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_file_disables_emails(self):
        self.assertIsNone(load_email_config("does_not_exist.toml"))

    def test_complete_config_with_defaults(self):
        path = self.write_config(
            '[email]\nsender = "s@gmail.com"\napp_password = "pw"\nrecipients = ["r@example.com"]\n'
        )
        self.assertEqual(load_email_config(path), {
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "sender": "s@gmail.com",
            "app_password": "pw",
            "recipients": ["r@example.com"],
            "min_interval": 60.0,
        })

    def test_incomplete_config_disables_emails(self):
        path = self.write_config('[email]\nsender = "s@gmail.com"\n')
        with mock.patch("builtins.print"):
            self.assertIsNone(load_email_config(path))

    def test_example_config_is_valid(self):
        example = os.path.join(os.path.dirname(__file__), "..", "email_config.example.toml")
        self.assertIsNotNone(load_email_config(example))


if __name__ == "__main__":
    unittest.main()
