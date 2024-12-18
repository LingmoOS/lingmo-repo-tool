"""Mail handling

@copyright: 2022  Ansgar <ansgar@debian.org>
@license: GNU General Public License version 2 or later
"""

import daklib.gpg

import email
import email.message
import email.policy

from typing import cast


def sign_mail(msg: email.message.EmailMessage, *, digest_algorithm: str = "SHA256", **kwargs) -> email.message.EmailMessage:
    """sign an email message using GnuPG.

    This only handles non-multipart messages.
    """
    mime_data = email.message.MIMEPart()
    mime_data.set_content(msg.get_payload())
    # Copy Content-Transfer-Encoding from unsigned message
    del mime_data["Content-Transfer-Encoding"]
    mime_data["Content-Transfer-Encoding"] = msg["Content-Transfer-Encoding"]
    data = mime_data.as_bytes(policy=email.policy.SMTP)

    sig = daklib.gpg.sign(data, **kwargs, digest_algorithm=digest_algorithm)
    mime_sig = email.message.MIMEPart()
    mime_sig['Content-Type'] = 'application/pgp-signature'
    mime_sig.set_payload(sig)

    msg.clear_content()
    del msg['Content-Type']
    msg['Content-Type'] = f'multipart/signed; micalg="pgp-{digest_algorithm.lower()}"; protocol="application/pgp-signature"'
    msg.set_payload([mime_data, mime_sig])
    return msg


# TODO [python3.10, pep604]:
# def parse_mail(msg: bytes | str) -> email.message.EmailMessage:
def parse_mail(msg) -> email.message.EmailMessage:
    if isinstance(msg, str):
        # We need a cast as the return type depends on the `policy` argument.
        return cast(email.message.EmailMessage, email.message_from_string(msg, policy=email.policy.SMTPUTF8))
    else:
        # We need a cast as the return type depends on the `policy` argument.
        return cast(email.message.EmailMessage, email.message_from_bytes(msg, policy=email.policy.SMTPUTF8))
