"""
Change Order Renderer — Generate client-facing documents and communications.

Produces two formats from drift detection results:
1. Formal change order (Markdown) — professional document for amendment
2. Email draft — softer framing for initial client outreach

Design: Markdown output (not PDF/DOCX) so partners can paste into their
engagement letter templates. Email draft is plain text for copy-paste.
"""

from datetime import date
from typing import List, Dict, Optional
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engagement_tracker import Engagement


# ---------------------------------------------------------------------------
# Change Order Renderer
# ---------------------------------------------------------------------------

class ChangeOrderRenderer:
    """Generates client-facing change order documents."""

    @staticmethod
    def render_change_order(
        engagement: Engagement,
        scope_additions: List[Dict],
        total_additional_hours: float,
        total_additional_cost: float,
        reason: str = "Client-requested scope expansion",
    ) -> str:
        """Generate a formal change order document in Markdown.

        Args:
            engagement: The engagement object
            scope_additions: List of dicts with keys: name, description, hours_already_spent,
                           hours_estimated_remaining, total_hours, assigned_to, total_cost
            total_additional_hours: Sum of hours across all additions
            total_additional_cost: Sum of costs across all additions
            reason: Why the scope changed

        Returns:
            Markdown-formatted change order document
        """
        lines = []

        # Header
        lines.append("# ENGAGEMENT AMENDMENT / CHANGE ORDER")
        lines.append("")
        lines.append(f"**Date:** {date.today().strftime('%B %d, %Y')}")
        lines.append(f"**Client:** {engagement.client_name}")
        lines.append(f"**Matter:** {engagement.matter_name}")
        lines.append(f"**Engagement ID:** {engagement.id}")
        lines.append(f"**Partner:** {engagement.responsible_partner}")
        lines.append("")

        # Background section
        lines.append("## BACKGROUND")
        lines.append("")
        original_dels = [d for d in engagement.deliverables if d.is_original_scope]
        lines.append(
            f"Our original engagement letter dated "
            f"{engagement.engagement_start.strftime('%B %d, %Y')} "
            f"covered the following scope of work:"
        )
        lines.append("")

        for i, d in enumerate(original_dels, 1):
            lines.append(f"{i}. **{d.name}**")
            lines.append(f"   {d.description}")
            lines.append("")

        lines.append(f"The fixed fee for this scope was **${engagement.fixed_fee:,.0f}**.")
        lines.append("")

        # Additional Scope section
        lines.append("## ADDITIONAL SCOPE")
        lines.append("")
        lines.append(f"**Reason:** {reason}")
        lines.append("")
        lines.append(
            "During the course of this engagement, the following additional "
            "work items have been identified:"
        )
        lines.append("")

        for i, addition in enumerate(scope_additions, 1):
            lines.append(f"### {i}. {addition['name']}")
            lines.append("")
            lines.append(f"{addition['description']}")
            lines.append("")

            hours_lines = []
            if addition.get("hours_already_spent", 0) > 0:
                hours_lines.append(
                    f"- Hours completed: {addition['hours_already_spent']:.1f}"
                )
            if addition.get("hours_estimated_remaining", 0) > 0:
                hours_lines.append(
                    f"- Hours remaining: {addition['hours_estimated_remaining']:.1f}"
                )
            hours_lines.append(f"- **Total hours:** {addition['total_hours']:.1f}")
            hours_lines.append(f"- **Cost:** ${addition['total_cost']:,.0f}")

            for line in hours_lines:
                lines.append(line)

            if addition.get("assigned_to"):
                assigned_str = ", ".join(addition["assigned_to"])
                lines.append(f"- Assigned to: {assigned_str}")

            lines.append("")

        # Fee Adjustment section
        lines.append("## FEE ADJUSTMENT")
        lines.append("")
        lines.append("| Item | Amount |")
        lines.append("|------|--------|")
        lines.append(f"| Original fixed fee | ${engagement.fixed_fee:,.0f} |")
        lines.append(f"| Additional scope | ${total_additional_cost:,.0f} |")
        lines.append(
            f"| **Revised fixed fee** | "
            f"**${engagement.fixed_fee + total_additional_cost:,.0f}** |"
        )
        lines.append("")

        increase_pct = (
            (total_additional_cost / engagement.fixed_fee * 100)
            if engagement.fixed_fee > 0 else 0
        )
        lines.append(
            f"This represents a {increase_pct:.1f}% increase over the original "
            f"engagement fee."
        )
        lines.append("")

        # Authorization section
        lines.append("## AUTHORIZATION")
        lines.append("")
        lines.append(
            "Please sign below to authorize the additional scope and revised fee. "
            "Work on the additional items will continue upon receipt of this signed amendment."
        )
        lines.append("")
        lines.append("")
        lines.append("**Client Signature:** ________________________     **Date:** ________________")
        lines.append("")
        lines.append(
            f"**{engagement.responsible_partner}** (on behalf of Firm)    "
            f"**Date:** ________________"
        )
        lines.append("")
        lines.append("*[Firm Name]*")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_email_draft(
        engagement: Engagement,
        scope_additions: List[Dict],
        total_additional_hours: float,
        total_additional_cost: float,
        reason: str = "items that require additional work",
    ) -> str:
        """Generate an email draft for client communication.

        Softer framing than formal change order. Suitable for initial outreach.

        Args:
            Same as render_change_order

        Returns:
            Plain text email draft
        """
        lines = []

        # Subject
        lines.append("[SUBJECT]")
        lines.append(f"Update on {engagement.matter_name} — Additional Work Items")
        lines.append("")

        # Body
        lines.append("[BODY]")
        lines.append("")
        lines.append(f"Dear {engagement.client_name},")
        lines.append("")
        lines.append(
            f"I wanted to touch base with you regarding {engagement.matter_name}. "
            f"As we've progressed through the engagement, a few additional work items "
            f"have come up that fall outside the scope of our original agreement."
        )
        lines.append("")

        lines.append("Specifically, we've identified the following:")
        lines.append("")

        for addition in scope_additions:
            lines.append(f"• {addition['name']}")
            lines.append(f"  {addition['description']}")
            lines.append(
                f"  Estimated effort: {addition['total_hours']:.1f} hours "
                f"(${addition['total_cost']:,.0f})"
            )
            lines.append("")

        lines.append(
            f"In total, these items represent an additional {total_additional_hours:.1f} hours "
            f"of work at a cost of ${total_additional_cost:,.0f}."
        )
        lines.append("")

        lines.append(
            "Rather than absorb this work into our fixed fee arrangement, "
            "I'd like to formalize it with an amendment to our engagement letter. "
            "This protects both of us by being explicit about scope."
        )
        lines.append("")

        lines.append("I'm attaching a formal change order for your review.")
        lines.append("")

        lines.append(
            "Please let me know if you have any questions or if you'd like to discuss "
            "any of these items."
        )
        lines.append("")

        lines.append("Best regards,")
        lines.append(engagement.responsible_partner)
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_html_change_order(
        engagement: Engagement,
        scope_additions: List[Dict],
        total_additional_hours: float,
        total_additional_cost: float,
        reason: str = "Client-requested scope expansion",
    ) -> str:
        """Generate an HTML version of the change order (for web display).

        Args:
            Same as render_change_order

        Returns:
            HTML document
        """
        lines = []

        lines.append("<!DOCTYPE html>")
        lines.append("<html>")
        lines.append("<head>")
        lines.append("<meta charset='utf-8'>")
        lines.append("<title>Change Order</title>")
        lines.append("<style>")
        lines.append("body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; ")
        lines.append("       max-width: 900px; margin: 40px auto; padding: 20px; }")
        lines.append("h1 { border-bottom: 2px solid #333; padding-bottom: 10px; }")
        lines.append("h2 { color: #333; margin-top: 30px; }")
        lines.append(".header-info { background: #f5f5f5; padding: 15px; margin-bottom: 20px; }")
        lines.append(".header-info p { margin: 5px 0; }")
        lines.append(".addition { border-left: 4px solid #0066cc; padding-left: 15px; ")
        lines.append("            margin-bottom: 20px; }")
        lines.append(".fee-table { border-collapse: collapse; width: 100%; margin: 15px 0; }")
        lines.append(".fee-table th, .fee-table td { border: 1px solid #ddd; ")
        lines.append("                                padding: 10px; text-align: left; }")
        lines.append(".fee-table th { background: #f5f5f5; }")
        lines.append(".signature-block { margin-top: 40px; }")
        lines.append(".signature-line { border-top: 1px solid #000; width: 250px; ")
        lines.append("                  margin-top: 30px; }")
        lines.append("</style>")
        lines.append("</head>")
        lines.append("<body>")

        # Header
        lines.append("<h1>ENGAGEMENT AMENDMENT / CHANGE ORDER</h1>")
        lines.append("<div class='header-info'>")
        lines.append(f"<p><strong>Date:</strong> {date.today().strftime('%B %d, %Y')}</p>")
        lines.append(f"<p><strong>Client:</strong> {engagement.client_name}</p>")
        lines.append(f"<p><strong>Matter:</strong> {engagement.matter_name}</p>")
        lines.append(f"<p><strong>Engagement ID:</strong> {engagement.id}</p>")
        lines.append(f"<p><strong>Partner:</strong> {engagement.responsible_partner}</p>")
        lines.append("</div>")

        # Background
        lines.append("<h2>BACKGROUND</h2>")
        original_dels = [d for d in engagement.deliverables if d.is_original_scope]
        lines.append(
            f"<p>Our original engagement letter dated "
            f"{engagement.engagement_start.strftime('%B %d, %Y')} "
            f"covered the following scope of work:</p>"
        )
        lines.append("<ol>")
        for d in original_dels:
            lines.append(f"<li><strong>{d.name}</strong><br/>{d.description}</li>")
        lines.append("</ol>")
        lines.append(
            f"<p>The fixed fee for this scope was <strong>${engagement.fixed_fee:,.0f}</strong>.</p>"
        )

        # Additional Scope
        lines.append("<h2>ADDITIONAL SCOPE</h2>")
        lines.append(f"<p><strong>Reason:</strong> {reason}</p>")
        lines.append(
            "<p>During the course of this engagement, the following additional "
            "work items have been identified:</p>"
        )

        for i, addition in enumerate(scope_additions, 1):
            lines.append(f"<div class='addition'>")
            lines.append(f"<h3>{i}. {addition['name']}</h3>")
            lines.append(f"<p>{addition['description']}</p>")
            lines.append("<ul>")

            if addition.get("hours_already_spent", 0) > 0:
                lines.append(
                    f"<li>Hours completed: {addition['hours_already_spent']:.1f}</li>"
                )
            if addition.get("hours_estimated_remaining", 0) > 0:
                lines.append(
                    f"<li>Hours remaining: {addition['hours_estimated_remaining']:.1f}</li>"
                )

            lines.append(f"<li><strong>Total hours:</strong> {addition['total_hours']:.1f}</li>")
            lines.append(f"<li><strong>Cost:</strong> ${addition['total_cost']:,.0f}</li>")
            lines.append("</ul>")
            lines.append("</div>")

        # Fee Adjustment
        lines.append("<h2>FEE ADJUSTMENT</h2>")
        lines.append("<table class='fee-table'>")
        lines.append("<tr><th>Item</th><th>Amount</th></tr>")
        lines.append(f"<tr><td>Original fixed fee</td><td>${engagement.fixed_fee:,.0f}</td></tr>")
        lines.append(
            f"<tr><td>Additional scope</td><td>${total_additional_cost:,.0f}</td></tr>"
        )
        lines.append(
            f"<tr><td><strong>Revised fixed fee</strong></td>"
            f"<td><strong>${engagement.fixed_fee + total_additional_cost:,.0f}</strong></td></tr>"
        )
        lines.append("</table>")

        increase_pct = (
            (total_additional_cost / engagement.fixed_fee * 100)
            if engagement.fixed_fee > 0 else 0
        )
        lines.append(
            f"<p>This represents a {increase_pct:.1f}% increase over the original "
            f"engagement fee.</p>"
        )

        # Authorization
        lines.append("<h2>AUTHORIZATION</h2>")
        lines.append(
            "<p>Please sign below to authorize the additional scope and revised fee. "
            "Work on the additional items will continue upon receipt of this signed amendment.</p>"
        )

        lines.append("<div class='signature-block'>")
        lines.append("<p><strong>Client:</strong></p>")
        lines.append("<div class='signature-line'></div>")
        lines.append("<p style='margin-top: 5px;'>Signature</p>")

        lines.append("<p style='margin-top: 30px;'><strong>Date:</strong></p>")
        lines.append("<div class='signature-line' style='width: 150px;'></div>")

        lines.append("<p style='margin-top: 30px;'><strong>For Firm:</strong></p>")
        lines.append(f"<p>{engagement.responsible_partner}</p>")
        lines.append("<div class='signature-line'></div>")
        lines.append("<p style='margin-top: 5px;'>Signature</p>")

        lines.append("<p style='margin-top: 30px;'><strong>Date:</strong></p>")
        lines.append("<div class='signature-line' style='width: 150px;'></div>")

        lines.append("</div>")

        lines.append("</body>")
        lines.append("</html>")

        return "\n".join(lines)
