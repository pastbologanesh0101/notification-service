import pytest

from app.templating import TemplateRenderError, UnknownTemplateError, render_notification


def test_welcome_template_substitutes_variables():
    body = render_notification(
        "welcome",
        {"user_name": "Ada", "product_name": "TransportLab", "email": "ada@example.com"},
    )
    assert "Ada" in body
    assert "TransportLab" in body
    assert "ada@example.com" in body
    assert "{{" not in body  # nothing left unrendered


def test_order_shipped_template_substitutes_variables():
    body = render_notification(
        "order_shipped",
        {
            "user_name": "Grace",
            "order_id": "ORD-42",
            "carrier": "FastShip",
            "tracking_url": "https://track.example.com/ORD-42",
            "eta": "2026-09-20",
            "product_name": "Acme",
        },
    )
    assert "ORD-42" in body
    assert "FastShip" in body
    assert "https://track.example.com/ORD-42" in body
    assert "2026-09-20" in body


def test_unknown_template_raises_clear_error():
    with pytest.raises(UnknownTemplateError) as exc_info:
        render_notification("does_not_exist", {})
    assert "does_not_exist" in str(exc_info.value)


def test_missing_template_variable_raises_render_error():
    with pytest.raises(TemplateRenderError):
        render_notification("welcome", {"user_name": "Ada"})  # missing product_name/email
