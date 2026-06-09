from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]


class MailSendPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = str(REPO)
        if root not in sys.path:
            sys.path.insert(0, root)

    def test_profile_rejects_ssl_and_starttls_together(self) -> None:
        from plugins.mail_send import MailProfile

        with self.assertRaises(ValueError):
            MailProfile(
                smtp_host="smtp.example.com",
                from_addr="a@example.com",
                use_ssl=True,
                use_starttls=True,
            )

    def test_send_mail_requires_recipient(self) -> None:
        from plugins.mail_send import MailProfile, send_mail

        profile = MailProfile(smtp_host="smtp.example.com", from_addr="a@example.com")
        with self.assertRaises(ValueError):
            send_mail(profile, subject="x", body="y")

    @patch("plugins.mail_send.send.smtplib.SMTP")
    def test_send_mail_starttls(self, mock_smtp_cls: MagicMock) -> None:
        from plugins.mail_send import MailProfile, send_mail

        smtp = MagicMock()
        smtp.send_message.return_value = {}
        mock_smtp_cls.return_value = smtp

        profile = MailProfile(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user@example.com",
            password="secret",
            from_addr="user@example.com",
            from_name="Tester",
            to_addrs=["recv@example.com"],
            use_starttls=True,
            use_ssl=False,
        )

        result = send_mail(profile, subject="hello", body="plain text")

        mock_smtp_cls.assert_called_once()
        smtp.ehlo.assert_called()
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("user@example.com", "secret")
        smtp.send_message.assert_called_once()
        smtp.quit.assert_called_once()
        self.assertEqual(result.recipients, ("recv@example.com",))
        self.assertIsNotNone(result.message_id)

    @patch("plugins.mail_send.send.smtplib.SMTP_SSL")
    def test_send_mail_ssl(self, mock_smtp_ssl_cls: MagicMock) -> None:
        from plugins.mail_send import MailProfile, send_mail

        smtp = MagicMock()
        smtp.send_message.return_value = {}
        mock_smtp_ssl_cls.return_value = smtp

        profile = MailProfile(
            smtp_host="smtp.example.com",
            smtp_port=465,
            from_addr="a@example.com",
            to_addrs=["b@example.com"],
            use_ssl=True,
            use_starttls=False,
        )

        send_mail(profile, subject="s", body="b", html=True)

        mock_smtp_ssl_cls.assert_called_once()
        sent_msg = smtp.send_message.call_args[0][0]
        self.assertTrue(sent_msg.is_multipart())
        self.assertEqual(sent_msg.get_content_type(), "multipart/alternative")
