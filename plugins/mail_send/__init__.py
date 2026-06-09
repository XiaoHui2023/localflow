from __future__ import annotations

from .models import MailProfile, MailSendResult
from .send import send_mail

__all__ = [
    "MailProfile",
    "MailSendResult",
    "send_mail",
]
