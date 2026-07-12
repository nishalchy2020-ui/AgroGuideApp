import logging
import smtplib
from email.message import EmailMessage

import requests
from flask import current_app, render_template, url_for

logger = logging.getLogger("agroguide.email")


def absolute_url(endpoint, **values):
    base_url = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    path = url_for(endpoint, **values)
    if base_url:
        return f"{base_url}{path}"
    return url_for(endpoint, _external=True, **values)


def send_verification_email(user, token):
    verify_url = absolute_url("auth.verify_email", token=token)
    _send_template_email(
        user.email,
        "Verify your AgroGuide email",
        "emails/verify_email.html",
        user=user,
        verify_url=verify_url,
    )


def send_welcome_email(user):
    _send_template_email(
        user.email,
        "Welcome to AgroGuide",
        "emails/welcome.html",
        user=user,
    )


def send_password_reset_email(user, token):
    reset_url = absolute_url("auth.reset_password", token=token)
    _send_template_email(
        user.email,
        "Reset your AgroGuide password",
        "emails/forgot_password.html",
        user=user,
        reset_url=reset_url,
    )


def send_password_changed_email(user, changed_at, ip_address=None, user_agent=None):
    _send_template_email(
        user.email,
        "Your AgroGuide password was changed",
        "emails/password_changed.html",
        user=user,
        changed_at=changed_at,
        ip_address=ip_address or "Not available",
        user_agent=user_agent or "Not available",
    )


def send_outbreak_alert_email(user, alert):
    _send_template_email(
        user.email,
        f"Disease outbreak alert: {alert['disease_label']}",
        "emails/outbreak_alert.html",
        user=user,
        alert=alert,
    )


def is_email_transport_configured():
    return bool(
        current_app.config.get("NODEMAILER_ENDPOINT")
        or current_app.config.get("SMTP_HOST")
    )


def _send_template_email(to_email, subject, template, **context):
    html = render_template(template, **context)
    text = _html_to_text(html)
    _send_email(to_email, subject, html, text)


def _send_email(to_email, subject, html, text):
    endpoint = current_app.config.get("NODEMAILER_ENDPOINT")
    if endpoint:
        _send_with_nodemailer(endpoint, to_email, subject, html, text)
        return

    if current_app.config.get("SMTP_HOST"):
        _send_with_smtp(to_email, subject, html, text)
        return

    logger.warning("Email not sent because no email transport is configured: %s", subject)


def _send_with_nodemailer(endpoint, to_email, subject, html, text):
    headers = {}
    api_key = current_app.config.get("NODEMAILER_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(
        endpoint,
        json={
            "from": current_app.config["MAIL_FROM"],
            "to": to_email,
            "subject": subject,
            "html": html,
            "text": text,
        },
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()


def _send_with_smtp(to_email, subject, html, text):
    message = EmailMessage()
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(
        current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=10
    ) as smtp:
        if current_app.config.get("SMTP_USE_TLS"):
            smtp.starttls()
        if current_app.config.get("SMTP_USER"):
            smtp.login(
                current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"]
            )
        smtp.send_message(message)


def _html_to_text(html):
    return " ".join(html.replace("<", " <").split())
