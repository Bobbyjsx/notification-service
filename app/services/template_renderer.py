import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.errors import TemplateRenderError

logger = logging.getLogger(__name__)

# Template Definitions with required variables
TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {
    "identity.email_verification": {
        "required_fields": ["otp"],
        "default_subject": "Verify your email address",
        "text_content": "Hello {{ first_name | default('') }},\n\nYour verification code is: {{ otp }}\n\nThis code expires in {{ expiration_minutes | default(30) }} minutes.\nIf you did not request this, you can ignore this email.",
    },
    "identity.password_reset": {
        "required_fields": ["reset_url"],
        "default_subject": "Reset your password",
        "text_content": "Hello {{ first_name | default('') }},\n\nReset your password by visiting:\n{{ reset_url }}\n\nThis link expires in {{ expiration_minutes | default(30) }} minutes.\nIf you did not request this, please secure your account.",
    },
    "payment.completed": {
        "required_fields": ["amount", "currency", "receipt_id"],
        "default_subject": "Payment Receipt",
        "text_content": "Hello {{ first_name | default('') }},\n\nPayment Confirmation\n\nReceipt ID: {{ receipt_id }}\nAmount: {{ currency }} {{ amount }}\nDate: {{ payment_date | default('Today') }}",
    },
    "ai.response_completed": {
        "required_fields": ["task_title"],
        "default_subject": "AI Processing Completed",
        "text_content": "Hello {{ first_name | default('') }},\n\nYour AI task '{{ task_title }}' has completed.\n{% if summary %}\nSummary: {{ summary }}\n{% endif %}{% if result_url %}\nView results: {{ result_url }}\n{% endif %}",
    },
    "general.notification": {
        "required_fields": ["body"],
        "default_subject": "Notification",
        "text_content": "Hello {{ first_name | default('') }},\n\n{{ title | default('Notification') }}\n\n{{ body }}\n{% if action_url %}\n{{ action_text | default('Link') }}: {{ action_url }}\n{% endif %}",
    },
}


class TemplateRenderer:
    """Renders HTML and text bodies for email templates using filesystem templates."""

    def __init__(self) -> None:
        template_dir = Path(__file__).parent.parent / "mail_templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def validate_template_context(self, template_id: str, context: dict[str, Any]) -> None:
        """Ensures all required fields for the template are provided in the context."""
        template_def = TEMPLATE_REGISTRY.get(template_id)
        if not template_def:
            raise TemplateRenderError(f"Unknown template ID: '{template_id}'")

        missing = [f for f in template_def["required_fields"] if f not in context or context[f] is None]
        if missing:
            raise TemplateRenderError(
                f"Missing required context fields for template '{template_id}': {', '.join(missing)}",
                details={"template_id": template_id, "missing_fields": missing},
            )

    def render(
        self,
        template_id: str,
        context: dict[str, Any],
        subject: str | None = None,
    ) -> tuple[str, str, str]:
        """
        Renders template into (resolved_subject, html_body, text_body).
        """
        template_def = TEMPLATE_REGISTRY.get(template_id)
        if not template_def:
            raise TemplateRenderError(f"Unknown template ID: '{template_id}'")

        self.validate_template_context(template_id, context)

        resolved_subject = subject or template_def.get("default_subject", "Notification")
        
        # We assume the HTML file is named `<template_id>.html`
        template_filename = f"{template_id}.html"

        try:
            html_tmpl = self.jinja_env.get_template(template_filename)
            text_tmpl = self.jinja_env.from_string(template_def["text_content"])

            render_ctx = {
                "subject": resolved_subject,
                **context,
            }

            rendered_html = html_tmpl.render(render_ctx)
            rendered_text = text_tmpl.render(render_ctx)

            return resolved_subject, rendered_html, rendered_text
        except Exception as exc:
            raise TemplateRenderError(f"Failed to render template '{template_id}': {exc}") from exc


template_renderer = TemplateRenderer()
