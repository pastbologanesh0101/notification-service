"""Jinja2-based rendering of the bundled notification templates."""

import os

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, UndefinedError

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
)

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    undefined=StrictUndefined,
    trim_blocks=True,
)


class UnknownTemplateError(Exception):
    """Raised when a caller asks for a template that does not exist."""


class TemplateRenderError(Exception):
    """Raised when a template references a variable that was not supplied."""


def available_templates():
    return sorted(name[:-4] for name in os.listdir(TEMPLATES_DIR) if name.endswith(".txt"))


def render_notification(template_name, template_vars=None):
    """Render ``<template_name>.txt`` with the given variables.

    Raises ``UnknownTemplateError`` if no such template file exists, and
    ``TemplateRenderError`` if a variable referenced by the template was not
    provided in ``template_vars``.
    """
    try:
        template = _env.get_template(f"{template_name}.txt")
    except TemplateNotFound:
        raise UnknownTemplateError(
            f"Unknown template: '{template_name}'. Available templates: "
            f"{', '.join(available_templates())}"
        )

    try:
        return template.render(**(template_vars or {}))
    except UndefinedError as exc:
        raise TemplateRenderError(f"Missing template variable: {exc}")
