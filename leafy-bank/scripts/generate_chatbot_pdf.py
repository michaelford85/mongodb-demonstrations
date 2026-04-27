#!/usr/bin/env python3
"""
Generates personal-banking-terms-conditions.pdf for the Leafy Bank chatbot service.

The chatbot's RAG pipeline chunks and embeds this document, then answers user
questions against it. Content covers the topics a demo user is most likely to ask:
accounts, transfers, fees, cards, overdrafts, disputes, and privacy.

Usage:
    python3 scripts/generate_chatbot_pdf.py
Output:
    services/chatbot/backend/data/fsi/leafy_bank_assistant/pdfs/
        personal-banking-terms-conditions.pdf
"""

import os
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# ── Output path ───────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT  = SCRIPT_DIR.parent
OUT_DIR    = REPO_ROOT / "services" / "chatbot" / "backend" / "data" / "fsi" / "leafy_bank_assistant" / "pdfs"
OUT_FILE   = OUT_DIR / "personal-banking-terms-conditions.pdf"

# ── Document content ──────────────────────────────────────────────────────────
SECTIONS = [
    {
        "title": "1. Introduction and Scope",
        "body": [
            ("paragraph", """
These Personal Banking Terms and Conditions ("Agreement") govern the relationship between
Leafy Bank ("the Bank", "we", "us") and each individual customer ("you", "your") who holds
a personal deposit account, payment account, or uses any personal banking service offered by
Leafy Bank. By opening an account or using our services you confirm that you have read,
understood, and agreed to this Agreement in its entirety.
"""),
            ("paragraph", """
This Agreement should be read alongside the Leafy Bank Privacy Notice, the Schedule of
Fees and Charges, and any product-specific terms provided at account opening. In the event
of a conflict, product-specific terms take precedence over this Agreement, and this Agreement
takes precedence over any general marketing material.
"""),
            ("paragraph", """
Leafy Bank reserves the right to update these terms at any time. We will provide at least
30 days' prior written notice of material changes via email to your registered address or
via a secure in-app message. Continued use of your account after the effective date of
changes constitutes acceptance of the revised terms.
"""),
        ]
    },
    {
        "title": "2. Account Opening and Eligibility",
        "body": [
            ("paragraph", """
To open a personal account with Leafy Bank you must: (a) be at least 18 years of age;
(b) be a resident of an eligible jurisdiction as published on our website; (c) provide
satisfactory proof of identity and address in accordance with our Know Your Customer (KYC)
procedures; and (d) not be subject to any legal restriction that would prevent you from
entering into a binding contract.
"""),
            ("paragraph", """
We perform identity verification in compliance with applicable anti-money-laundering (AML)
regulations. We may use third-party credit reference or identity verification agencies for
this purpose. A soft credit check may be performed at account opening; this will not affect
your credit score.
"""),
            ("paragraph", """
Account opening is subject to approval by Leafy Bank at our sole discretion. We may decline
an application without providing a reason, subject to applicable law.
"""),
        ]
    },
    {
        "title": "3. Account Types",
        "body": [
            ("paragraph", """
Leafy Bank offers the following personal account types. Full product details, including
applicable interest rates and features, are available within the Leafy Bank app and on
our website.
"""),
            ("table", {
                "headers": ["Account Type", "Minimum Balance", "Monthly Fee", "Key Features"],
                "rows": [
                    ["Everyday Checking", "$0", "$0", "Unlimited transactions, debit card, mobile deposits"],
                    ["Premium Checking", "$1,500 avg. daily", "$12 (waivable)", "Fee waived if balance ≥ $1,500 or direct deposit ≥ $500/mo"],
                    ["High-Yield Savings", "$100", "$0", "4.50% APY, up to 6 withdrawals per month"],
                    ["Money Market", "$2,500", "$15 (waivable)", "Tiered interest, check-writing, fee waived if balance ≥ $2,500"],
                    ["Student Checking", "$0", "$0", "Age 16–24, no minimum balance, no overdraft fees"],
                ],
            }),
            ("paragraph", """
Interest rates on savings and money market accounts are variable and may change at any time.
We will notify you of rate changes by publishing updated rates in the app. The Annual
Percentage Yield (APY) shown assumes interest is compounded daily and credited monthly.
"""),
        ]
    },
    {
        "title": "4. Deposits",
        "body": [
            ("paragraph", """
You may deposit funds into your account through the following channels: (a) direct deposit
from an employer or government agency; (b) mobile check deposit via the Leafy Bank app;
(c) wire transfer from a domestic or international financial institution; (d) ACH transfer
from an account held at another US bank; (e) cash deposit at an in-network ATM.
"""),
            ("paragraph", """
Funds availability for deposited items is governed by our Funds Availability Policy,
summarised as follows:
"""),
            ("table", {
                "headers": ["Deposit Method", "Next Business Day", "Full Availability"],
                "rows": [
                    ["Direct Deposit / ACH", "Full amount", "Same day"],
                    ["Wire Transfer (domestic)", "Full amount", "Same day as receipt"],
                    ["Wire Transfer (international)", "Full amount", "1–2 business days"],
                    ["Mobile Check Deposit (≤ $500)", "$200 provisional", "2nd business day"],
                    ["Mobile Check Deposit (> $500)", "$200 provisional", "5th business day"],
                    ["ATM Cash Deposit", "Full amount", "Same business day"],
                ],
            }),
            ("paragraph", """
We reserve the right to delay availability of deposited funds in accordance with applicable
law if we have reasonable cause to believe the deposited item will not be honoured, or if
the account has been open for fewer than 30 days.
"""),
        ]
    },
    {
        "title": "5. Withdrawals and Transfers",
        "body": [
            ("paragraph", """
You may withdraw funds or initiate transfers subject to the following limits. Limits may
be temporarily reduced for security reasons without prior notice.
"""),
            ("table", {
                "headers": ["Transfer Type", "Daily Limit", "Monthly Limit", "Processing Time"],
                "rows": [
                    ["Internal (Leafy Bank to Leafy Bank)", "$50,000", "Unlimited", "Instant"],
                    ["ACH — Standard", "$25,000", "$100,000", "1–3 business days"],
                    ["ACH — Same Day", "$10,000", "$50,000", "Same business day (if initiated before 2:30 PM ET)"],
                    ["Domestic Wire", "$100,000", "$500,000", "Same business day (if initiated before 4:00 PM ET)"],
                    ["International Wire", "$50,000", "$200,000", "1–5 business days"],
                    ["ATM Withdrawal", "$1,000", "$5,000", "Instant"],
                    ["Debit Card (point-of-sale)", "$5,000", "$20,000", "Instant (authorization)"],
                ],
            }),
            ("paragraph", """
International wire transfers may be subject to correspondent bank fees and currency
conversion charges in addition to Leafy Bank's standard wire fee. The exchange rate applied
will be the rate available to Leafy Bank at the time of processing, which may differ from
published mid-market rates.
"""),
            ("paragraph", """
For savings and money market accounts, federal Regulation D previously limited certain
withdrawal types to six per month. Although this restriction was suspended by the Federal
Reserve in April 2020, Leafy Bank may impose an Excessive Withdrawal Fee of $10 per
withdrawal beyond six in a calendar month on savings accounts, as disclosed in the Schedule
of Fees and Charges.
"""),
        ]
    },
    {
        "title": "6. Debit Cards",
        "body": [
            ("paragraph", """
Upon opening an Everyday Checking, Premium Checking, or Money Market account, Leafy Bank
will issue you a Visa® Debit Card linked to your primary account. You will receive the card
within 7–10 business days of account approval. Expedited delivery (2–3 business days) is
available for a $15 fee.
"""),
            ("paragraph", """
Your debit card can be used at any merchant or ATM that accepts Visa worldwide. Leafy Bank
does not charge fees for ATM withdrawals at in-network ATMs (Allpoint® network, 55,000+
locations). Out-of-network ATM withdrawals are subject to a $2.50 fee per transaction,
plus any fee charged by the ATM operator.
"""),
            ("paragraph", """
If your card is lost, stolen, or compromised, you must report it immediately via the Leafy
Bank app (Card Controls → Report Lost/Stolen) or by calling our 24/7 customer service line.
A replacement card will be issued within 7–10 business days (standard) or 2–3 business days
(expedited, $15 fee). Your liability for unauthorized transactions is governed by Section 10
of this Agreement.
"""),
            ("paragraph", """
You may temporarily freeze your debit card at any time through the app without cancelling
it. Frozen cards will decline all transactions except pre-authorized recurring payments and
ATM PIN transactions at Leafy Bank ATMs.
"""),
        ]
    },
    {
        "title": "7. Overdraft Policy",
        "body": [
            ("paragraph", """
Leafy Bank offers two overdraft management options. You must select your preferred option
during account setup; you may change your selection at any time in the app.
"""),
            ("paragraph", """
Option A — Standard Overdraft Coverage: We may, at our discretion, authorize and pay
transactions (checks, ACH debits, and one-time debit card transactions if separately
opted in) that overdraw your account. Each overdraft item paid is subject to an Overdraft
Fee of $32. We will not charge more than 4 Overdraft Fees per business day ($128 maximum
per day). No overdraft fee is charged if the account is overdrawn by $10 or less at the
end of the business day.
"""),
            ("paragraph", """
Option B — No Overdraft / Decline: Transactions that would overdraw your account are
declined at no charge. Checks and ACH debits returned unpaid are subject to a Returned
Item Fee of $32 per item (maximum 4 per business day).
"""),
            ("paragraph", """
Overdraft Protection Link: Regardless of the option selected above, you may link an Leafy
Bank savings or money market account as an overdraft protection source. If your checking
account would be overdrawn, funds are automatically transferred from the linked account in
$100 increments. An Overdraft Transfer Fee of $10 applies per transfer day (not per
transfer). This fee is waived for Premier Checking customers and for linked High-Yield
Savings accounts.
"""),
            ("paragraph", """
We will notify you by push notification and email each time your account goes into overdraft.
If a negative balance remains after 30 calendar days, the account may be referred to a
collections agency and reported to ChexSystems.
"""),
        ]
    },
    {
        "title": "8. Fees and Charges",
        "body": [
            ("paragraph", """
A full Schedule of Fees and Charges is provided at account opening and is available at any
time within the Leafy Bank app under Settings → Documents → Fee Schedule. The most common
fees are summarised below. All fees are subject to change with 30 days' notice.
"""),
            ("table", {
                "headers": ["Fee Type", "Amount", "Notes"],
                "rows": [
                    ["Monthly Maintenance (Everyday Checking)", "$0", "Always waived"],
                    ["Monthly Maintenance (Premium Checking)", "$12", "Waived: avg. daily balance ≥ $1,500 or direct deposit ≥ $500"],
                    ["Monthly Maintenance (Money Market)", "$15", "Waived: avg. daily balance ≥ $2,500"],
                    ["Overdraft Fee", "$32", "Max 4/day; waived if overdrawn ≤ $10"],
                    ["Returned Item Fee", "$32", "Max 4/day"],
                    ["Overdraft Transfer Fee", "$10/day", "Waived: Premier Checking; linked HY Savings"],
                    ["Domestic Wire (outgoing)", "$25", "Waived 1×/month for Premier Checking"],
                    ["International Wire (outgoing)", "$45", "Plus correspondent bank fees"],
                    ["Wire (incoming, domestic)", "$0", ""],
                    ["Wire (incoming, international)", "$15", ""],
                    ["Stop Payment", "$30", "Per item; valid 6 months; renewable"],
                    ["Paper Statement", "$3/month", "eStatements always free"],
                    ["Expedited Card Delivery", "$15", "2–3 business days"],
                    ["Out-of-Network ATM Withdrawal", "$2.50", "Plus operator fee"],
                    ["Foreign Transaction Fee", "2%", "On debit card transactions in foreign currency"],
                    ["Cashier's Check", "$10", ""],
                    ["Account Research / Copy", "$25/hour", "Minimum 1 hour"],
                ],
            }),
        ]
    },
    {
        "title": "9. Interest Rates",
        "body": [
            ("paragraph", """
Interest rates on deposit accounts are variable and set by Leafy Bank based on prevailing
market conditions and the Federal Funds Rate. Rates may be changed at any time. The following
rates were in effect at the time of printing; current rates are always displayed in the app.
"""),
            ("table", {
                "headers": ["Account", "APY", "Compounding", "Crediting"],
                "rows": [
                    ["Everyday Checking", "0.01%", "Daily", "Monthly"],
                    ["Premium Checking", "0.10%", "Daily", "Monthly"],
                    ["High-Yield Savings", "4.50%", "Daily", "Monthly"],
                    ["Money Market — $0–$9,999", "2.00%", "Daily", "Monthly"],
                    ["Money Market — $10,000–$49,999", "3.00%", "Daily", "Monthly"],
                    ["Money Market — $50,000+", "3.75%", "Daily", "Monthly"],
                    ["Student Checking", "0.01%", "Daily", "Monthly"],
                ],
            }),
            ("paragraph", """
Interest is calculated on the daily collected balance using the daily periodic rate (APY
divided by 365). Interest begins accruing on the business day we receive your deposit.
If you close your account before interest is credited, accrued but unpaid interest will
be paid at account closing.
"""),
        ]
    },
    {
        "title": "10. Unauthorized Transactions and Your Liability",
        "body": [
            ("paragraph", """
You must review your account statements and transaction history promptly and report any
unauthorized or erroneous transactions to Leafy Bank as soon as possible.
"""),
            ("paragraph", """
Electronic Fund Transfers (EFT): Your liability for unauthorized EFT transactions is
governed by the Electronic Fund Transfer Act (EFTA) and Regulation E. If you notify us
within 2 business days of learning of the unauthorized transaction, your maximum liability
is $50. If you notify us after 2 business days but within 60 calendar days of the statement
date on which the unauthorized transaction first appeared, your maximum liability is $500.
If you fail to notify us within 60 calendar days, you may be liable for the full amount
of transactions that occurred after the 60-day period.
"""),
            ("paragraph", """
Visa® Zero Liability Policy: For unauthorized transactions made with your Leafy Bank Visa®
Debit Card (whether in-store, online, or via contactless), you are protected by the Visa®
Zero Liability Policy, provided you: (a) exercised reasonable care in safeguarding your card
from loss or theft, and (b) have not reported two or more unauthorized events in the prior
12-month period. Visa® Zero Liability does not apply to commercial card transactions or
ATM transactions not processed by Visa.
"""),
            ("paragraph", """
To report an unauthorized transaction, use the app (Transactions → [transaction] → Dispute)
or call our 24/7 fraud line. We will acknowledge your dispute within 3 business days,
provide a provisional credit within 10 business days (or 5 business days for point-of-sale
transactions) where required by law, and complete our investigation within 45 days
(90 days for international or new account transactions).
"""),
        ]
    },
    {
        "title": "11. Account Closure",
        "body": [
            ("paragraph", """
You may close your account at any time by submitting a closure request via the Leafy Bank
app (Settings → Account → Close Account) or by contacting customer service. We may require
you to maintain the account for up to 10 business days to allow pending transactions to
settle. Any remaining balance will be remitted to you by check mailed to your address of
record, or by ACH transfer to a linked external account of your choice, within 5 business
days of closure.
"""),
            ("paragraph", """
Leafy Bank may close your account at any time with 30 days' notice if: (a) your account
has had a zero balance for more than 180 consecutive days; (b) you have violated any
provision of this Agreement; (c) we are required to do so by law or regulatory order.
We may close your account immediately without notice if we detect fraudulent activity or
if required by law enforcement.
"""),
            ("paragraph", """
Accounts closed with a negative balance remain your obligation. You agree to repay any
negative balance within 30 days of closure. Uncollected negative balances may be reported
to credit reporting agencies and referred to collections.
"""),
        ]
    },
    {
        "title": "12. Joint Accounts",
        "body": [
            ("paragraph", """
Where an account is held by two or more persons ("joint account"), each account holder
has full authority to make deposits, withdrawals, and transfers without the consent of
the other account holder(s). Each account holder is jointly and severally liable for all
debts, fees, and obligations arising from the account.
"""),
            ("paragraph", """
Joint accounts are held with right of survivorship (JTWROS) unless otherwise specified
at account opening. Upon the death of one account holder, the surviving account holder(s)
assume full ownership of the account balance, subject to applicable estate and tax law.
"""),
            ("paragraph", """
Either account holder may request removal of the other joint holder; however, removal
requires written consent from the account holder being removed, except where prohibited
by a court order. Adding a joint holder requires consent from all existing account holders
and satisfactory identity verification of the new holder.
"""),
        ]
    },
    {
        "title": "13. Privacy and Data Protection",
        "body": [
            ("paragraph", """
Leafy Bank is committed to protecting your personal information. Our full Privacy Notice
is available at leafybank.com/privacy and within the app. The following is a summary of
our key data practices.
"""),
            ("paragraph", """
Information We Collect: We collect information you provide directly (name, address, Social
Security Number, date of birth, contact details), information generated by your use of our
services (transaction history, login activity, device information), and information from
third parties (credit bureaus, identity verification services, fraud prevention providers).
"""),
            ("paragraph", """
How We Use Your Information: We use your data to (a) open and maintain your account;
(b) process transactions; (c) comply with legal and regulatory obligations including AML and
OFAC screening; (d) detect and prevent fraud; (e) communicate with you about your account;
(f) improve our products and services; and (g) with your consent, provide personalised
offers and marketing communications.
"""),
            ("paragraph", """
Information Sharing: We share information with (a) service providers who assist in our
operations under strict data processing agreements; (b) regulatory and law enforcement
bodies as required by law; (c) other financial institutions to complete transfers you
initiate; and (d) with your explicit consent, third-party financial applications you
connect via our Open Finance feature.
"""),
            ("paragraph", """
Your Rights: Subject to applicable law, you may request access to, correction of, or
deletion of your personal data, or object to certain processing activities, by contacting
privacy@leafybank.com or via the app (Settings → Privacy → My Data Rights). We will
respond within 30 calendar days.
"""),
            ("paragraph", """
Data Retention: We retain your data for the period required by applicable law, generally
a minimum of 7 years from account closure for transaction records.
"""),
        ]
    },
    {
        "title": "14. Governing Law and Dispute Resolution",
        "body": [
            ("paragraph", """
This Agreement is governed by the laws of the State of Delaware, United States, without
regard to conflict-of-law principles, and applicable federal law.
"""),
            ("paragraph", """
Informal Resolution: Before initiating formal dispute proceedings, you agree to contact
Leafy Bank customer service and allow us 30 days to attempt to resolve the issue informally.
"""),
            ("paragraph", """
Arbitration: Subject to the exceptions below, any dispute, claim, or controversy arising
out of or relating to this Agreement or your account that cannot be resolved informally
shall be resolved by binding individual arbitration administered by the American Arbitration
Association (AAA) under its Consumer Arbitration Rules. The arbitration will be conducted
in English. You may opt out of this arbitration clause within 60 days of account opening by
sending written notice to: Leafy Bank Legal Department, Dispute Resolution, 123 Finance
Street, Wilmington, DE 19801.
"""),
            ("paragraph", """
Class Action Waiver: To the fullest extent permitted by law, you waive your right to
participate in any class action lawsuit or class-wide arbitration against Leafy Bank.
"""),
            ("paragraph", """
Exceptions to Arbitration: Either party may bring an individual claim in small claims court.
Either party may seek emergency injunctive or other equitable relief in a court of competent
jurisdiction to prevent irreparable harm.
"""),
        ]
    },
    {
        "title": "15. Amendments and Entire Agreement",
        "body": [
            ("paragraph", """
This Agreement, together with the Schedule of Fees and Charges, the Privacy Notice, and
any product-specific terms, constitutes the entire agreement between you and Leafy Bank
regarding your personal banking relationship and supersedes all prior communications,
representations, and agreements.
"""),
            ("paragraph", """
If any provision of this Agreement is found to be invalid or unenforceable, the remaining
provisions will continue in full force and effect.
"""),
            ("paragraph", """
Our failure to enforce any provision of this Agreement shall not constitute a waiver of
our right to enforce it in the future.
"""),
            ("paragraph", """
This Agreement is effective as of January 1, 2025. Last updated: March 15, 2025.
"""),
        ]
    },
]


# ── PDF builder ───────────────────────────────────────────────────────────────

GREEN  = colors.HexColor("#00684A")   # MongoDB brand green
DKGRAY = colors.HexColor("#2C3E50")
LTGRAY = colors.HexColor("#F5F7FA")
MGRAY  = colors.HexColor("#D0D5DD")


def build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title",
        fontName="Helvetica-Bold",
        fontSize=26,
        textColor=GREEN,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    styles["cover_sub"] = ParagraphStyle(
        "cover_sub",
        fontName="Helvetica",
        fontSize=13,
        textColor=DKGRAY,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    styles["cover_date"] = ParagraphStyle(
        "cover_date",
        fontName="Helvetica-Oblique",
        fontSize=10,
        textColor=colors.grey,
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    styles["section_title"] = ParagraphStyle(
        "section_title",
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=GREEN,
        spaceBefore=18,
        spaceAfter=6,
        keepWithNext=True,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    return styles


def make_table(headers, rows):
    col_widths_map = {
        2: [2.5 * inch, 4.5 * inch],
        3: [2.5 * inch, 1.5 * inch, 3.0 * inch],
        4: [1.8 * inch, 1.3 * inch, 1.2 * inch, 2.7 * inch],
    }
    n = len(headers)
    col_widths = col_widths_map.get(n)

    table_data = [headers] + rows
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 6),
        ("TOPPADDING",   (0, 0), (-1, 0), 6),
        # Body rows
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8.5),
        ("TOPPADDING",   (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LTGRAY]),
        # Grid
        ("GRID",         (0, 0), (-1, -1), 0.5, MGRAY),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def build_pdf(out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=LETTER,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        title="Leafy Bank — Personal Banking Terms and Conditions",
        author="Leafy Bank",
    )

    styles = build_styles()
    story = []

    # ── Cover page ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.8 * inch))
    story.append(Paragraph("🌿 Leafy Bank", styles["cover_title"]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(HRFlowable(width="60%", thickness=2, color=GREEN, hAlign="CENTER"))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Personal Banking", styles["cover_sub"]))
    story.append(Paragraph("Terms and Conditions", styles["cover_sub"]))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Effective January 1, 2025 · Last updated March 15, 2025", styles["cover_date"]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("Leafy Bank · 123 Finance Street · Wilmington, DE 19801", styles["cover_date"]))
    story.append(Paragraph("Member FDIC · Equal Housing Lender", styles["cover_date"]))
    story.append(PageBreak())

    # ── Sections ──────────────────────────────────────────────────────────────
    for section in SECTIONS:
        story.append(Paragraph(section["title"], styles["section_title"]))
        story.append(HRFlowable(width="100%", thickness=0.5, color=MGRAY))
        story.append(Spacer(1, 4))

        for kind, content in section["body"]:
            if kind == "paragraph":
                story.append(Paragraph(content.strip(), styles["body"]))
            elif kind == "table":
                story.append(Spacer(1, 4))
                story.append(make_table(content["headers"], content["rows"]))
                story.append(Spacer(1, 8))

    doc.build(story)
    print(f"✅  Written: {out_path}")
    print(f"   Size:    {out_path.stat().st_size / 1024:.1f} KB")
    print(f"   Sections: {len(SECTIONS)}")


if __name__ == "__main__":
    build_pdf(OUT_FILE)
