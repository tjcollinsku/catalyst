"""
Deterministic referral package PDF generator.

Produces a professional, citation-bearing PDF document that a government
investigator (AG, IRS, FBI) can read in 15 minutes and act on. Every claim
traces back to a specific document, finding, or data point. No AI, no
randomness — the output is deterministic.

Structure:
    1. Cover page
    2. Executive summary
    3. Subject entities (table)
    4. Findings (per-finding sections with citations)
    5. Financial summary (year-over-year analysis)
    6. Document index (chain of custody, SHA-256 hashes)
    7. Appendix (raw evidence snapshots)
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class ReferralPDFGenerator:
    """Generate a deterministic, citation-bearing referral package PDF."""

    def __init__(self):
        """Initialize styles and layout parameters."""
        self.pagesize = letter
        self.width, self.height = self.pagesize
        self.styles = getSampleStyleSheet()
        self._build_custom_styles()

    def _build_custom_styles(self):
        """Build custom paragraph styles for the document."""
        # Define custom styles, avoiding duplicates of existing styles
        style_defs = [
            ParagraphStyle(
                name="CoverTitle",
                parent=self.styles["Heading1"],
                fontSize=28,
                textColor=colors.HexColor("#1a1a1a"),
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
            ),
            ParagraphStyle(
                name="CoverSubtitle",
                parent=self.styles["Normal"],
                fontSize=14,
                textColor=colors.HexColor("#444444"),
                spaceAfter=6,
                alignment=TA_CENTER,
                fontName="Helvetica",
            ),
            ParagraphStyle(
                name="SectionHeading",
                parent=self.styles["Heading2"],
                fontSize=14,
                textColor=colors.HexColor("#1a1a1a"),
                spaceAfter=10,
                spaceBefore=12,
                fontName="Helvetica-Bold",
            ),
            ParagraphStyle(
                name="FindingTitle",
                parent=self.styles["Heading3"],
                fontSize=12,
                textColor=colors.HexColor("#2c3e50"),
                spaceAfter=6,
                spaceBefore=10,
                fontName="Helvetica-Bold",
            ),
            ParagraphStyle(
                name="ReferralBodyText",
                parent=self.styles["Normal"],
                fontSize=10,
                leading=14,
                spaceAfter=8,
                alignment=TA_LEFT,
            ),
            ParagraphStyle(
                name="Citation",
                parent=self.styles["Normal"],
                fontSize=8,
                textColor=colors.HexColor("#666666"),
                spaceAfter=4,
                leftIndent=0.2 * inch,
                fontName="Courier",
            ),
        ]

        for style in style_defs:
            if style.name not in self.styles:
                self.styles.add(style)

    def generate(self, case, findings, entities, documents, financials):
        """
        Generate the referral package PDF.

        Args:
            case: Case model instance
            findings: Queryset of CONFIRMED findings with DOCUMENTED or
                      TRACED evidence_weight
            entities: Dict with keys 'persons' and 'organizations' (querysets)
            documents: Queryset of all documents in the case
            financials: Queryset of FinancialSnapshot objects

        Returns:
            BytesIO object containing the PDF data
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.pagesize,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title=f"Referral Package — {case.name}",
            author="Catalyst Investigation Platform",
        )

        story = []

        # Cover page
        story.extend(self._build_cover_page(case))
        story.append(PageBreak())

        # Executive summary
        story.extend(self._build_executive_summary(case, findings))
        story.append(PageBreak())

        # Subject entities
        story.extend(
            self._build_subject_entities(
                entities.get("persons", []),
                entities.get("organizations", []),
            )
        )
        story.append(PageBreak())

        # Findings (one per confirmed finding)
        if findings.exists():
            story.extend(self._build_findings_section(findings))
            story.append(PageBreak())

        # Financial summary
        if financials.exists():
            story.extend(self._build_financial_summary(financials))
            story.append(PageBreak())

        # Document index
        story.extend(self._build_document_index(documents))
        story.append(PageBreak())

        # Appendix (evidence snapshots)
        story.extend(self._build_appendix(findings))

        # Build and finalize PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def _build_cover_page(self, case):
        """Build the cover page."""
        story = []

        story.append(Spacer(1, 1.5 * inch))
        story.append(
            Paragraph("REFERRAL PACKAGE", self.styles["CoverTitle"])
        )
        story.append(
            Paragraph(
                f"Case: {case.name}",
                self.styles["CoverSubtitle"],
            )
        )
        story.append(Spacer(1, 0.3 * inch))

        generated_date = datetime.now().strftime("%B %d, %Y")
        story.append(
            Paragraph(
                f"Generated: {generated_date}",
                self.styles["CoverSubtitle"],
            )
        )
        story.append(Spacer(1, 0.3 * inch))

        status_badge = (
            f"Status: <b>{case.status}</b>"
            if case.status
            else "Status: Unknown"
        )
        story.append(
            Paragraph(status_badge, self.styles["CoverSubtitle"])
        )

        story.append(Spacer(1, 1.5 * inch))
        story.append(
            Paragraph(
                (
                    "<b>CONFIDENTIAL</b><br/>"
                    "FOR LAW ENFORCEMENT USE ONLY"
                ),
                self.styles["CoverSubtitle"],
            )
        )

        return story

    def _build_executive_summary(self, case, findings):
        """Build the executive summary section."""
        story = []

        story.append(
            Paragraph("EXECUTIVE SUMMARY", self.styles["SectionHeading"])
        )

        # Summary table
        persons_count = case.persons.count()
        orgs_count = case.organizations.count()
        docs_count = case.documents.count()
        findings_count = findings.count()

        summary_data = [
            ["Metric", "Count"],
            ["Subject Persons", str(persons_count)],
            ["Subject Organizations", str(orgs_count)],
            ["Documents", str(docs_count)],
            ["Confirmed Findings", str(findings_count)],
        ]

        summary_table = Table(
            summary_data,
            colWidths=[3.5 * inch, 1.5 * inch],
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0),
                     colors.HexColor("#e8e8e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS",
                     (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f5f5f5")]),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 0.2 * inch))

        # Overview paragraph
        if case.notes:
            overview_text = f"{case.notes}"
        else:
            overview_text = (
                f"This referral package summarizes the investigation of "
                f"<b>{case.name}</b>. The investigation identified "
                f"<b>{findings_count}</b> confirmed findings supported by "
                f"<b>{docs_count}</b> documents across "
                f"<b>{persons_count}</b> persons and "
                f"<b>{orgs_count}</b> organizations."
            )

        story.append(Paragraph(overview_text, self.styles["ReferralBodyText"]))

        return story

    def _build_subject_entities(self, persons, organizations):
        """Build the subject entities section."""
        story = []

        story.append(
            Paragraph(
                "SUBJECT ENTITIES",
                self.styles["SectionHeading"],
            )
        )

        if persons or organizations:
            story.append(
                Paragraph("Persons", self.styles["FindingTitle"])
            )
            if persons:
                person_data = [
                    ["Name", "Role Tags", "Address", "Tax ID"]
                ]
                for p in persons:
                    roles = ", ".join(p.role_tags) if p.role_tags else "—"
                    person_data.append(
                        [
                            p.full_name,
                            roles,
                            p.address or "—",
                            p.tax_id or "—",
                        ]
                    )

                person_table = Table(
                    person_data,
                    colWidths=[
                        1.5 * inch,
                        1.2 * inch,
                        1.8 * inch,
                        1.0 * inch,
                    ],
                )
                person_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0),
                             colors.HexColor("#e8e8e8")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("FONTNAME", (0, 0), (-1, 0),
                             "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                            ("TOPPADDING", (0, 0), (-1, 0), 4),
                            ("GRID", (0, 0), (-1, -1), 0.5,
                             colors.grey),
                            ("ROWBACKGROUNDS",
                             (0, 1), (-1, -1),
                             [colors.white, colors.HexColor(
                                 "#f5f5f5")]),
                        ]
                    )
                )
                story.append(person_table)
                story.append(Spacer(1, 0.2 * inch))

            story.append(
                Paragraph("Organizations", self.styles["FindingTitle"])
            )
            if organizations:
                org_data = [
                    ["Name", "Type", "EIN", "Status", "Address"]
                ]
                for o in organizations:
                    org_data.append(
                        [
                            o.name,
                            o.get_org_type_display() or "—",
                            o.ein or "—",
                            o.status or "—",
                            o.address or "—",
                        ]
                    )

                org_table = Table(
                    org_data,
                    colWidths=[
                        1.5 * inch,
                        1.0 * inch,
                        1.0 * inch,
                        0.8 * inch,
                        1.7 * inch,
                    ],
                )
                org_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0),
                             colors.HexColor("#e8e8e8")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("FONTNAME", (0, 0), (-1, 0),
                             "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                            ("TOPPADDING", (0, 0), (-1, 0), 4),
                            ("GRID", (0, 0), (-1, -1), 0.5,
                             colors.grey),
                            ("ROWBACKGROUNDS",
                             (0, 1), (-1, -1),
                             [colors.white, colors.HexColor(
                                 "#f5f5f5")]),
                        ]
                    )
                )
                story.append(org_table)
        else:
            story.append(
                Paragraph(
                    "No subject entities.",
                    self.styles["ReferralBodyText"],
                )
            )

        return story

    def _build_findings_section(self, findings):
        """Build the findings section (one per confirmed finding)."""
        story = []

        story.append(
            Paragraph("FINDINGS", self.styles["SectionHeading"])
        )

        for idx, finding in enumerate(findings, start=1):
            story.append(
                Paragraph(
                    f"{idx}. {finding.title} [{finding.severity}]",
                    self.styles["FindingTitle"],
                )
            )

            # Evidence weight badge
            story.append(
                Paragraph(
                    (
                        f"<b>Rule:</b> {finding.rule_id or 'MANUAL'} | "
                        f"<b>Evidence:</b> {finding.evidence_weight}"
                    ),
                    self.styles["Citation"],
                )
            )
            story.append(Spacer(1, 0.1 * inch))

            # Description
            if finding.description:
                story.append(
                    Paragraph(
                        f"<b>Detection:</b> {finding.description}",
                        self.styles["ReferralBodyText"],
                    )
                )

            # Narrative
            if finding.narrative:
                story.append(
                    Paragraph(
                        f"<b>Analysis:</b> {finding.narrative}",
                        self.styles["ReferralBodyText"],
                    )
                )

            # Linked entities
            entity_links = finding.entity_links.all()
            if entity_links.exists():
                entities_text = ", ".join(
                    [
                        el.context_note or f"Entity ID {el.entity_id}"
                        for el in entity_links
                    ]
                )
                story.append(
                    Paragraph(
                        f"<b>Linked Entities:</b> {entities_text}",
                        self.styles["ReferralBodyText"],
                    )
                )

            # Linked documents with citations
            doc_links = finding.document_links.all()
            if doc_links.exists():
                story.append(
                    Paragraph(
                        "<b>Evidence Documents:</b>",
                        self.styles["ReferralBodyText"],
                    )
                )
                for doc_link in doc_links:
                    doc = doc_link.document
                    page_ref = (
                        f", p.{doc_link.page_reference}"
                        if doc_link.page_reference
                        else ""
                    )
                    context = (
                        f" ({doc_link.context_note})"
                        if doc_link.context_note
                        else ""
                    )
                    citation = (
                        f"• {doc.filename}{page_ref}{context}"
                    )
                    story.append(
                        Paragraph(
                            citation,
                            self.styles["Citation"],
                        )
                    )

            # Legal references
            if finding.legal_refs:
                refs_text = "; ".join(finding.legal_refs)
                story.append(
                    Paragraph(
                        f"<b>Legal Basis:</b> {refs_text}",
                        self.styles["Citation"],
                    )
                )

            story.append(Spacer(1, 0.25 * inch))

        return story

    def _build_financial_summary(self, financials):
        """Build the financial summary section."""
        story = []

        story.append(
            Paragraph(
                "FINANCIAL SUMMARY",
                self.styles["SectionHeading"],
            )
        )

        # Group financials by organization
        financials = financials.select_related("organization").order_by(
            "organization__name", "tax_year"
        )

        if not financials.exists():
            story.append(
                Paragraph(
                    "No financial data available.",
                    self.styles["ReferralBodyText"],
                )
            )
            return story

        # Build one table per organization
        current_org = None
        org_financials = []

        for fs in financials:
            if current_org != fs.organization:
                if org_financials:
                    # Flush the previous organization's table
                    story.extend(
                        self._build_org_financial_table(
                            current_org,
                            org_financials,
                        )
                    )
                    story.append(Spacer(1, 0.2 * inch))
                current_org = fs.organization
                org_financials = []
            org_financials.append(fs)

        # Don't forget the last organization
        if org_financials:
            story.extend(
                self._build_org_financial_table(
                    current_org,
                    org_financials,
                )
            )

        return story

    def _build_org_financial_table(self, organization, financials):
        """Build financial table for one organization."""
        story = []

        story.append(
            Paragraph(
                f"{organization.name}",
                self.styles["FindingTitle"],
            )
        )

        # Build table data
        table_data = [
            [
                "Tax Year",
                "Total Revenue",
                "Total Expenses",
                "Net Assets",
            ]
        ]

        for fs in sorted(financials, key=lambda x: x.tax_year or 0):
            year_str = str(fs.tax_year) if fs.tax_year else "—"
            revenue_str = (
                f"${fs.total_revenue:,.0f}"
                if fs.total_revenue is not None
                else "—"
            )
            expenses_str = (
                f"${fs.total_expenses:,.0f}"
                if fs.total_expenses is not None
                else "—"
            )
            assets_str = (
                f"${fs.net_assets_eoy:,.0f}"
                if fs.net_assets_eoy is not None
                else "—"
            )

            table_data.append([year_str, revenue_str, expenses_str,
                               assets_str])

        table = Table(
            table_data,
            colWidths=[1.0 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0),
                     colors.HexColor("#e8e8e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                    ("TOPPADDING", (0, 0), (-1, 0), 4),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS",
                     (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f5f5f5")]),
                ]
            )
        )
        story.append(table)

        return story

    def _build_document_index(self, documents):
        """Build the document index with SHA-256 chain of custody."""
        story = []

        story.append(
            Paragraph(
                "DOCUMENT INDEX",
                self.styles["SectionHeading"],
            )
        )

        story.append(
            Paragraph(
                (
                    "This section lists all source documents with their "
                    "cryptographic hashes. The hash serves as a tamper-evident "
                    "seal for chain of custody."
                ),
                self.styles["ReferralBodyText"],
            )
        )
        story.append(Spacer(1, 0.15 * inch))

        if not documents.exists():
            story.append(
                Paragraph(
                    "No documents.",
                    self.styles["ReferralBodyText"],
                )
            )
            return story

        # Build document table
        docs = documents.order_by("uploaded_at")
        doc_data = [["#", "Filename", "Type", "SHA-256 Hash"]]

        for idx, doc in enumerate(docs, start=1):
            # Truncate long filenames
            filename = (
                doc.filename[:40] + "..."
                if len(doc.filename) > 40
                else doc.filename
            )
            # Truncate long hash for readability
            hash_display = (
                doc.sha256_hash[:16] + "..."
                if len(doc.sha256_hash) > 16
                else doc.sha256_hash
            )
            doc_data.append(
                [
                    str(idx),
                    filename,
                    doc.get_doc_type_display() or "—",
                    hash_display,
                ]
            )

        doc_table = Table(
            doc_data,
            colWidths=[0.5 * inch, 2.0 * inch, 1.0 * inch, 2.0 * inch],
        )
        doc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0),
                     colors.HexColor("#e8e8e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (1, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                    ("TOPPADDING", (0, 0), (-1, 0), 4),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS",
                     (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f5f5f5")]),
                    ("FONTNAME", (0, 1), (-1, -1), "Courier"),
                    ("FONTSIZE", (3, 1), (3, -1), 7),
                ]
            )
        )
        story.append(doc_table)

        return story

    def _build_appendix(self, findings):
        """Build the appendix with raw evidence snapshots."""
        story = []

        story.append(
            Paragraph(
                "APPENDIX: EVIDENCE SNAPSHOTS",
                self.styles["SectionHeading"],
            )
        )

        story.append(
            Paragraph(
                (
                    "This appendix contains the raw JSON evidence data "
                    "captured at detection time. This information is provided "
                    "for forensic reviewers who need the underlying data."
                ),
                self.styles["ReferralBodyText"],
            )
        )
        story.append(Spacer(1, 0.15 * inch))

        if not findings.exists():
            story.append(
                Paragraph(
                    "No findings.",
                    self.styles["ReferralBodyText"],
                )
            )
            return story

        import json

        for finding in findings:
            if not finding.evidence_snapshot:
                continue

            story.append(
                Paragraph(
                    f"{finding.rule_id or 'MANUAL'}: {finding.title}",
                    self.styles["FindingTitle"],
                )
            )

            # Pretty-print JSON
            json_str = json.dumps(
                finding.evidence_snapshot,
                indent=2,
                default=str,
            )
            # Truncate very long JSON
            if len(json_str) > 500:
                json_str = json_str[:500] + "\n[truncated...]"

            story.append(
                Paragraph(
                    f"<pre>{json_str}</pre>",
                    self.styles["Citation"],
                )
            )
            story.append(Spacer(1, 0.15 * inch))

        return story
