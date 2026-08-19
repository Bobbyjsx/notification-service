import pytest

from app.core.errors import TemplateRenderError
from app.services.template_renderer import TemplateRenderer


def test_render_email_verification():
    renderer = TemplateRenderer()
    context = {"otp": "839201", "app_name": "Auth Platform"}
    subject, html_body, text_body = renderer.render("identity.email_verification", context)

    assert "Verify your email address" in subject
    assert "839201" in html_body
    assert "Auth Platform" in html_body
    assert "839201" in text_body


def test_render_password_reset():
    renderer = TemplateRenderer()
    context = {"reset_url": "https://auth.example.com/reset?token=xyz", "app_name": "Auth Platform"}
    subject, html_body, text_body = renderer.render("identity.password_reset", context)

    assert "Reset your password" in subject
    assert "https://auth.example.com/reset?token=xyz" in html_body
    assert "https://auth.example.com/reset?token=xyz" in text_body


def test_render_missing_required_context_raises():
    renderer = TemplateRenderer()
    # Missing 'otp'
    context = {"app_name": "Auth Platform"}
    with pytest.raises(TemplateRenderError) as exc_info:
        renderer.render("identity.email_verification", context)
    assert "Missing required context fields" in str(exc_info.value)


def test_render_unknown_template_raises():
    renderer = TemplateRenderer()
    with pytest.raises(TemplateRenderError) as exc_info:
        renderer.render("nonexistent.template", {})
    assert "Unknown template ID" in str(exc_info.value)
