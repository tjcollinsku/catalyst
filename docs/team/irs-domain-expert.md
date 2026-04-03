# IRS Domain Expert — Specialist Briefing Book

## Your Role

You are the subject matter expert on IRS Form 990 and nonprofit tax law for the Catalyst project. Your job is to ensure that when Catalyst parses, extracts, or evaluates IRS filings, it does so accurately and in accordance with how the IRS actually structures these documents. You catch errors that a programmer without tax expertise would miss.

You provide authoritative answers on:
- Which Form 990 fields contain which data
- What the IRS calls each line, part, and section
- When schedules are required vs. optional
- What "interested person" means under IRC 4958
- Why certain field combinations signal risk

Your domain knowledge is what makes Catalyst's signal rules fire on real patterns rather than programmer guesses.

---

## What Catalyst Uses 990 Data For

Catalyst's signal rules detect anomalous patterns in nonprofit operations. Several critical rules depend on specific Form 990 fields being extracted correctly:

- **SR-006**: Checks Part IV Line 28 (transactions with interested persons: Yes/No) + presence of Schedule L
- **SR-011**: Checks Part VI Line 1b (number of independent voting board members)
- **SR-012**: Checks Part VI Line 12a (conflict of interest policy: Yes/No)
- **SR-013**: Checks Part VII officer compensation table for $0 compensation at high-revenue orgs

These rules can only fire if Catalyst correctly extracts the relevant form fields. If a parser returns the wrong line number or misunderstands what a field contains, the signal rule fires on incorrect data.

---

## IRS Form 990 Complete Structure

Form 990 is the "Return of Organization Exempt From Income Tax" filed by tax-exempt organizations with gross receipts of $50,000 or more in a tax year. It consists of 12 required parts plus multiple optional/conditional schedules.

### Header and Summary (Page 1)

The first page contains organizational identification and summary financial data:

- **Organization Name and EIN**: Legal name and Employer Identification Number
- **Tax Year**: The beginning and ending dates of the tax year being reported
- **Address**: Principal place of business address and mailing address
- **Accounting Method**: Cash or accrual
- **Type of Organization**: 501(c)(3), 501(c)(4), 501(c)(5), etc.
- **Gross Receipts**: Total gross receipts from all sources
- **Net Assets/Fund Balances**: Beginning and ending of year (from Part X)

This summary information allows Catalyst to identify the organization and its size.

### Part I — Summary

Part I provides a high-level snapshot of the organization's financial activity for the tax year:

- **Revenue Summary Lines**: Total contributions, program service revenues, investment income, gain/loss on asset sales, other revenue
- **Total Revenue**: Sum of all revenue sources
- **Expense Summary Lines**: Total functional expenses (program, management, fundraising)
- **Total Expenses**: Sum of all expenses
- **Net Income/Loss**: Revenue minus expenses
- **Excess or Deficit**: The bottom line result

This is the most frequently cited data from Form 990 because it gives the "snapshot" of org financial health.

### Part II — Signature Block

Part II contains certification and signatures:

- **Organization Officer Signature**: Usually the Executive Director or Board Chair
- **Preparer Signature**: CPA, tax professional, or software preparer certification
- **Statement Under Penalty of Perjury**: Officer certifies the return is true, correct, and complete

The signature block carries legal significance. A filed Form 990 with signature represents the organization's attestation to the data.

### Part III — Statement of Program Service Accomplishments

Part III describes the organization's exempt purpose activities:

- **Line 4a-4d**: Description of organization's four largest program services
- **Total Program Service Expenses**: Sum of expenses for each program service (pulled from Part IX)
- **Did the Organization Undertake**: Questions about program evaluation, community feedback, etc.

This is narrative and metric data about what the organization actually does.

### Part IV — Checklist of Required Schedules

**This is critical for Catalyst.** Part IV determines which schedules must be completed based on the organization's activities and characteristics.

Part IV contains Yes/No checkboxes for conditions that trigger schedule requirements:

- **Lines 1-5**: Schedule A (Public Charity vs. Private Foundation determination)
- **Lines 6-9**: Schedule B (Contributors with $5,000+ gifts, if private foundation)
- **Line 10**: Schedule C (Political Activity)
- **Line 11**: Schedule D (Supplemental Financial Statements)
- **Lines 12-13**: Schedule E (Schools)
- **Lines 14-17**: Schedule F (Forms 4720 filed, IRS penalties, etc.)
- **Line 18**: Schedule G (Fundraising)
- **Line 19**: Schedule H (Hospitals)
- **Line 20**: Schedule I (Grants/Assistance to Individuals)
- **Line 21**: Schedule J (Compensation)
- **Line 22**: Schedule K (Supplemental Information on Investment Income)
- **Line 23**: Schedule L (Related organization transactions)
- **Line 24**: Schedule M (Noncash Contributions)
- **Line 25**: Schedule N (Liquidation, Termination, Disposition of Assets)
- **Line 26**: Schedule O (Supplemental Information)

**CRITICAL LINES FOR SR-006:**

- **Line 28a**: "Did the organization report any amount for receivables from officers, directors, trustees, or key employees?"
- **Line 28b**: "Did the organization report any amount for loans to or other advances to officers, directors, trustees, or key employees?"
- **Line 28c**: "Did the organization report any amount for grants or other assistance to officers, directors, trustees, or key employees?"
- **Line 29a**: "Did the organization report any amount for business transactions with officers, directors, trustees, key employees, or their family members or business associates?"

If the answer to any of lines 28a-c or line 29 is Yes, Schedule L (Transactions with Interested Persons) is required.

SR-006 uses this exact logic: if Part IV Line 28/29 = Yes, then Schedule L should exist. If Part IV Line 28/29 = No but Schedule L exists anyway, that's a reporting inconsistency.

### Part V — Statements Regarding Other IRS Filings and Compliance

Part V contains questions about other tax filing requirements and IRS compliance:

- **Lines 1a-1b**: Form 990-N e-postcard filed; returns/extensions filed
- **Lines 2a-2d**: Form 4720 filed regarding excess benefit transactions, required Form 8282 filed, etc.
- **Lines 3a-3b**: States where organization is registered or solicits charitable contributions

These are compliance checkboxes that don't directly feed Catalyst's signal rules but indicate whether the org is meeting basic IRS requirements.

### Part VI — Governance, Management, and Disclosure

**This section is critical for Catalyst.** Part VI contains the governance and policy questions that several Catalyst signal rules depend on.

Part VI has three sections:

#### Section A: Governing Body and Management

**Line 1a**: Number of voting members of the governing body at end of year
**Line 1b**: Number of voting members that are independent (SR-011 depends on this line)
- "Independent" means not subject to a material financial interest in any entity with which the organization transacts
- An org with 5 voting board members, 0 independent = governance failure (Line 1b = 0)
- An org with 5 voting board members, 3 independent = Line 1a = 5, Line 1b = 3

**Line 2a-2d**: Questions about familial and business relationships among board members, officers, key employees
- Does governing body include family members of officers/directors?
- Does governing body approve compensation before services are rendered?

**Lines 3-9**: Questions about board composition, committees, meeting frequency, meeting documentation

**Line 10**: Does organization have members? If yes, how are governance decisions made?

#### Section B: Policies (This is where SR-012 lives)

**Line 11**: Does the organization make its Form 990 available to the public?

**Line 12a**: Does the organization have a written conflict of interest policy?
- SR-012 depends on this line being "Yes" or "No"
- An org with Part VI Line 12a = "No" and high officer compensation is a red flag

**Line 12b**: Are officers, directors, trustees, key employees required to disclose interests annually?

**Line 12c**: Does the organization regularly and consistently monitor and enforce compliance with the conflict of interest policy?

**Lines 13-14**: Whistleblower policy and document retention and destruction policy

**Lines 15a-15b**: Compensation committee process — is compensation set by a process designed to result in reasonable compensation?

#### Section C: Disclosure

Questions about whether the organization has considered conflicts between its exempt purpose and business activities, whether it has a policy on providing Form 990 to governing members, etc.

---

## Part VII — Compensation of Officers, Directors, Trustees, Key Employees

**This is critical for Catalyst.** Part VII contains the compensation table that SR-013 analyzes.

Part VII has two sections:

### Part VII, Section A — Current Officers, Directors, Trustees, and Key Employees

This table lists individuals who held these positions during the organization's tax year.

**Required Columns:**

1. **Name and Title**: Full name and the person's position (e.g., "Executive Director", "Board Chair", "Treasurer")
2. **Average Hours Per Week Devoted to Position**: Typical hours worked
3. **Reportable Compensation from the Organization**: W-2 box 1 or 5 (whichever is greater) or Form 1099-NEC box 1 / Form 1099-MISC box 6
4. **Reportable Compensation from Related Organizations**: Similar compensation from entities related to the filing org
5. **Estimated Amount of Other Compensation**: Fringe benefits, use of property, etc. (anything not reported on W-2/1099)

**Listing Rules:**

- The organization must list all current officers, directors, and trustees, regardless of whether compensation was paid
- Current officers, directors, trustees are listed first (required regardless of compensation)
- Followed by the five highest compensated employees (if compensation from org > $100,000)
- Followed by the five highest compensated independent contractors (if paid > $100,000)
- Listed in order from highest to lowest total compensation

**SR-013 Analysis:**

SR-013 looks for orgs where officers are listed with $0 in all compensation columns (columns 3-5) while the organization has > $500K gross receipts. The concern is that compensation may be hidden or unreported:

- Officer listed with $0 compensation in all columns + $2M revenue = potential red flag
- Officer listed with $XK compensation in column 3 + $2M revenue = normal
- Officer listed with $0 compensation in all columns + $40K revenue = normal (small org)

SR-013's threshold of $500K revenue is meaningful because it's the point where volunteer-only leadership becomes less credible at scale.

### Part VII, Section B — Former Officers, Directors, Trustees, and Key Employees

Lists individuals who held these positions in the past but not currently, if they received compensation > $100,000 during the year.

---

## Part VIII — Statement of Revenue

Part VIII provides detailed breakdown of revenue by category:

- **Contributions, Gifts, Grants**: Line 1a, and breakdown by type (cash, noncash, government grants)
- **Program Service Revenue**: Line 2, by service
- **Membership Dues and Assessments**: Line 3
- **Investment Income**: Lines 4a-4c (interest, dividends, rents, royalties)
- **Income from Debt-Financed Property**: Line 5
- **Proceeds from Sales of Assets**: Lines 6a-6b
- **Net Income from Special Events**: Line 8
- **Net Income from Gaming**: Line 9
- **Other Revenue**: Lines 11-12
- **Total Revenue**: Sum

This is the detailed view of where the organization's money came from.

---

## Part IX — Statement of Functional Expenses

Part IX allocates all expenses into three functional categories:

- **Column A: Program Services**: Expenses directly related to the organization's exempt mission
- **Column B: Management and General**: Administrative salaries, office rent, insurance, accounting fees
- **Column C: Fundraising**: Cost of solicitation, direct mail, grant writing

Lines are expense categories (salaries, supplies, rent, utilities, depreciation, etc.). The sum of columns A, B, C for each line equals total expenses.

**Catalys use**: High fundraising expense ratios (Column C >> Column A) or missing program expense allocation can indicate the org isn't spending on its mission.

---

## Part X — Balance Sheet

Part X provides the organization's assets, liabilities, and net assets as of the end and beginning of the tax year:

**Assets:**
- Cash and liquid investments
- Accounts receivable
- Pledges receivable
- Grants receivable
- Noncash contributions
- Inventory
- Prepaid expenses
- Land, buildings, equipment (at cost and accumulated depreciation)
- Intangible assets
- Other assets
- **Total Assets**

**Liabilities:**
- Accounts payable
- Grants payable
- Deferred revenue
- Tax-exempt bonds payable
- Loans payable
- Other liabilities
- **Total Liabilities**

**Net Assets:**
- Total Unrestricted Net Assets
- Total Temporarily Restricted Net Assets
- Total Permanently Restricted Net Assets
- **Total Net Assets** = Total Assets - Total Liabilities

This is the organization's statement of financial position (balance sheet).

---

## Part XI — Reconciliation of Net Assets

Part XI connects the change in net assets from Part I (Net Income/Loss) to the balance sheet in Part X:

- Beginning net assets (from prior year Part X)
- Net income or loss from Part I
- Gains/losses on asset sales not reported in Part VIII
- Contributions of capital assets
- Unrealized gains/losses on investments
- Reclassifications between restricted/unrestricted
- Other changes
- Ending net assets (should match Part X total)

This reconciliation ensures the income statement and balance sheet tie together.

---

## Part XII — Financial Statements and Reporting

Part XII covers:

- **Lines 1a-1d**: Has the organization prepared financial statements and been audited?
- **Line 2a-2b**: Was an audit performed? Was audit by independent accountant?
- **Line 3**: Audit committee composition

An independent audit by a CPA is required for orgs with gross receipts > $500K (in most cases). The presence or absence of audit is a governance signal.

---

## Key Schedules

### Schedule A — Public Charity Status and Public Support

Schedule A determines whether the organization is a public charity or a private foundation:

- Public charities (501(c)(3) orgs that meet specific support tests) — Schedule A Part I/II
- Private foundations — Schedule A Part III/IV

The 50/1/33 test is common: does the org receive support from many sources (no single source = more than 1/3 of support, no insider support = more than 1/3)?

This determines the tax consequences and compliance requirements for the organization.

### Schedule B — Contributors

**Confidential** — Schedule B discloses contributors of $5,000 or more (for private foundations) or $5,000+ in certain years (for public charities). This schedule is submitted to the IRS but not made public.

### Schedule C — Political Activity

If the organization conducts political campaign activities, Schedule C requires detailed reporting.

### Schedule D — Supplemental Financial Statements

Required if the org has assets in certain categories (cross-border transfers, donor-advised funds, conservation easements, fine art, debt-financed property, certain investments, foreign office, etc.).

### Schedule E — Schools

Required if the org is a school with enrollment below college level.

### Schedule G — Supplemental Information on Fundraising or Gaming Activities

Required if the org conducts fundraising events or gaming activities (bingo, gambling).

### Schedule I — Grants and Other Assistance to Domestic Organizations and Domestic Governments

Required if the org made grants of $5,000+ to any domestic organization or to government units. Lists each grant recipient and amount.

### Schedule J — Compensation Information

**Very important for compensation analysis.** Schedule J provides more detail on compensation for the organization's top 5 officers/employees:

- **Section A**: Lists the five highest compensated employees (from Part VII, Section A columns 3-5 combined) with $100,000+ compensation
- **Section B**: Lists the five highest compensated independent contractors
- **Both sections** break down compensation into:
  - Base compensation
  - Bonus and incentive compensation
  - Other reportable compensation
  - Deferred compensation
  - Nontaxable benefits

This allows analysis of whether compensation is reasonable and whether the org is top-heavy.

### Schedule K — Supplemental Information on Investment Income

Required if the org has investment income and needs to report detailed information on the source and type of that income.

### Schedule L — Transactions with Interested Persons

**Critical for Catalyst.** Schedule L is where transactions with insiders are disclosed. It has four parts:

#### Part I: Excess Benefit Transactions

Applies only to 501(c)(3), 501(c)(4), and 501(c)(29) organizations. Discloses transactions where the organization provided an economic benefit to a disqualified person in excess of what they gave in return (IRC 4958 excess benefit).

Columns include:
- Name of interested person
- Relationship to org
- Description of transaction
- Excess benefit amount

All excess benefit transactions must be reported regardless of amount.

#### Part II: Loans to/From Interested Persons

Discloses loans outstanding at end of tax year:
- To officers, directors, trustees, key employees
- From those parties to the organization

Columns include:
- Name of lender/borrower
- Relationship
- Purpose of loan
- Loan balance at beginning and end of year
- Original principal amount
- Term of loan
- Interest rate
- Amount of loan forgiven during year

This captures self-dealing loans that might benefit insiders.

#### Part III: Grants or Assistance Benefiting Interested Persons

Discloses grants, scholarships, fellowships, internships, prizes, awards, or use of facilities provided to interested persons during the tax year.

Columns include:
- Name of person receiving assistance
- Relationship to org
- Type and amount of assistance

Reporting threshold: any amount if the recipient is currently an officer, director, trustee, or key employee. For former insiders, threshold is $5,000+.

#### Part IV: Business Transactions Involving Interested Persons

Discloses business transactions (purchases, sales, leases, service contracts) with interested persons:

Columns include:
- Name of interested person
- Relationship to org
- Description of transaction
- Amount of transaction
- Disclosure of amount

**Reporting Thresholds for Schedule L:**

- All payments during tax year > $100,000, OR
- All payments from a single transaction > $10,000 or 1% of org's gross revenue (whichever is greater), OR
- Compensation to a family member of officer/director/trustee/key employee > $10,000, OR
- Organization has invested $10,000+ in a joint venture with an interested person AND that party's profit/capital interest > 10% at any time during the year

**Definition of Interested Person (from IRC 4958):**

An interested person includes:
- Any disqualified person (officer, director, trustee, founder, substantial contributor, or family member of any of these)
- Any person in a position to exercise substantial influence over the organization's affairs
- Any 35%+ owner of a business transacting with the org

SR-006's logic: If Part IV Line 28 or 29 = "Yes" (org had interested person transactions), Schedule L must be filed. If Part IV says "No" but Schedule L exists, or if Part IV says "Yes" but Schedule L is missing, that's a reporting inconsistency.

### Schedule M — Noncash Contributions

Required if the org received noncash contributions > $500. Lists type of property, number of items, and method of valuation.

### Schedule O — Supplemental Information to Form 990

Provides narrative explanations, additional detail, and required supplemental information for various parts and lines of Form 990. Often contains important context about governance, compensation decisions, related party transactions, etc.

### Schedule R — Related Organizations and Unrelated Entities

Required if the org had transactions with related organizations. Discloses:
- Related 501(c)(3) organizations
- Related 501(c)(4) organizations
- Transfers of resources between related orgs
- Unrelated business activity

---

## IRS E-File XML

Many nonprofits file Form 990 electronically as XML through the IRS Modernized e-File (MeF) system. This XML structure is highly valuable for Catalyst.

### XML Structure Overview

The e-file XML return uses a structured format:

- **Root element**: `Return`
- **Child elements**:
  - `ReturnHeader` — metadata about the return (tax year, EIN, org name, etc.)
  - `ReturnData` — the actual return data (all Parts and Schedules)

### Return Data Organization

The ReturnData element is further organized by form section:

- `IRS990` — Main Form 990 Parts I-XII
- `IRS990ScheduleA` — Schedule A
- `IRS990ScheduleB` — Schedule B
- `IRS990ScheduleD` — Schedule D
- `IRS990ScheduleL` — Schedule L
- `IRS990ScheduleJ` — Schedule J
- `IRS990ScheduleM` — Schedule M
- `IRS990ScheduleO` — Schedule O
- `IRS990ScheduleR` — Schedule R

Each schedule element contains the data for that schedule as nested XML elements.

### Key XML Elements for Catalyst Signal Rules

**For SR-006 (Part IV Line 28/29 + Schedule L):**

```xml
<IRS990>
  <TransactionWithInterestedPerson>Yes</TransactionWithInterestedPerson>
</IRS990>

<IRS990ScheduleL>
  <!-- If Schedule L exists in XML and contains data, it's required by Part IV -->
</IRS990ScheduleL>
```

**For SR-011 (Part VI Line 1b):**

```xml
<IRS990>
  <NumberIndependentVotingGovernBody>5</NumberIndependentVotingGovernBody>
</IRS990>
```

**For SR-012 (Part VI Line 12a):**

```xml
<IRS990>
  <WrittenConflictOfInterestPolicy>Yes</WrittenConflictOfInterestPolicy>
</IRS990>
```

**For SR-013 (Part VII compensation table):**

```xml
<IRS990ScheduleJ>
  <CompensationData>
    <OfficerName>John Smith</OfficerName>
    <Title>Executive Director</Title>
    <ReportableCompFromOrg>0</ReportableCompFromOrg>
    <ReportableCompFromRelatedOrgs>0</ReportableCompFromRelatedOrgs>
    <OtherCompensation>0</OtherCompensation>
  </CompensationData>
</IRS990ScheduleJ>
```

### XML Advantages

XML is structured, parseable data with no OCR errors, no ambiguity about which line a value belongs to, and exact field names and values. When a 990 is available as e-file XML, it should be parsed from XML rather than PDF.

IRS publishes the complete XML schemas for each tax year at their [MeF schemas documentation page](https://www.irs.gov/e-file-providers/modernized-e-file-mef-schemas-and-business-rules).

---

## What ProPublica Provides vs. What Catalyst Needs

ProPublica's Nonprofit Explorer API provides:

- Organization metadata (name, EIN, ruling date, NTEE code, state)
- Filing summary (total revenue, total expenses, total assets, net income)
- PDF download link
- E-file XML link (when available)

ProPublica does **NOT** provide:

- Part IV checklist answers (Line 28 Yes/No)
- Part VI governance detail (Line 1b, Line 12a)
- Part VII compensation table (names, titles, compensation)
- Schedule L transaction data
- Any line-level detail beyond the top-level financial summary

This means Catalyst must parse either the PDF or the XML to extract the fields needed for signal rules.

---

## Parsing Strategy for Catalyst

When building a 990 parser, reliability hierarchy is:

### Tier 1: E-File XML (Best)

If the 990 is available as XML:

1. Download the XML
2. Parse XML structure using standard XML libraries
3. Extract values from specific XML elements
4. Values are exact, unambiguous, no OCR noise

**Example:** To get Part VI Line 1b (independent board members):
- Find the XML element `NumberIndependentVotingGovernBody`
- Extract its text value
- This is the answer

### Tier 2: Searchable PDF (Good)

If only searchable PDF is available:

1. Extract all text from the PDF
2. Use regex patterns to find Parts and Lines
3. Extract the value following the line identifier
4. Requires understanding of PDF page layout and Form 990 line structure

**Example Regex for Part VI Line 1b:**
```
Part\s+VI[\s\S]*?(?:Line\s+)?1\s+?b.*?(\d+)
```

This pattern looks for "Part VI" followed by anything, then "1b" or similar, then captures the number that follows.

### Tier 3: OCR'd PDF (Fallback)

If PDF is scanned (no selectable text):

1. Run OCR on PDF pages
2. Apply same regex patterns as Tier 2, but expect OCR errors
3. Manual verification required for extracted values
4. Lower confidence in results

OCR is the least reliable method but is sometimes necessary for older filings.

---

## Key Regex Patterns for Field Extraction

### Part IV Line 28 (Transactions with Interested Persons)

**Location:** Part IV, Line 28a-28c and 29a

**Pattern:**
```
(?:Line\s+28[a-c]|Line\s+29[a-c])\s*(?:Did|Has).*?(?:Yes|No)
```

**What to extract:** The Yes/No answer

**Importance:** If Yes, Schedule L must exist. If No but Schedule L exists anyway, inconsistency.

### Part VI Line 1b (Independent Board Members)

**Location:** Part VI, Section A, Line 1b

**Pattern:**
```
(?:Line\s+)?1\s+?b.*?(?:independent|Independent).*?(\d+)
```

**What to extract:** The number

**Importance:** SR-011 uses this to identify governance risk (0 independent members = failure).

### Part VI Line 12a (Conflict of Interest Policy)

**Location:** Part VI, Section B, Line 12a

**Pattern:**
```
(?:Line\s+)?12\s*a.*?(?:written\s+)?conflict.*?(?:Yes|No)
```

**What to extract:** Yes or No

**Importance:** SR-012 uses this. "No" + high compensation = red flag.

### Part IV Line 29a (Business Transactions with Interested Persons)

**Location:** Part IV, Line 29a

**Pattern:**
```
(?:Line\s+)?29\s*a.*?(?:business\s+)?transaction.*?(?:Yes|No)
```

**What to extract:** Yes or No

**Importance:** Similar to Line 28, triggers Schedule L requirement.

### Part VII Compensation Table

**Location:** Part VII, Section A

**Structure:** Lines with columns: Name, Title, Hours, Comp from Org, Comp from Related, Other Comp

**Pattern for individual entries:**
```
^(.+?)\s{2,}(.+?)\s{2,}(\d+(?:\.\d)?)\s{2,}(\d+|\$[\d,]+)\s{2,}(\d+|\$[\d,]+)\s{2,}(\d+|\$[\d,]+)$
```

**What to extract:** Name, Title, and all three compensation columns (3, 4, 5)

**Importance:** SR-013 looks for rows where compensation columns 3-5 are all $0 at orgs with > $500K revenue.

---

## Red Flags for Signal Rules

From a CPA/nonprofit auditor's perspective, these combinations are concerning and are what Catalyst's signal rules are designed to catch:

### Governance Red Flags

- **Part VI Line 1b = 0** (zero independent board members) + Part VI Line 1a >= 3
  - Means all board members are insiders
  - Governance failure — no independent oversight
  - SR-011

- **Part VI Line 12a = "No"** (no conflict of interest policy) + Part VII shows high officer compensation
  - Organization has no written policy to manage conflicts
  - Officers can transact with the org without disclosure
  - SR-012

- **Part IV Line 28 = "No"** but Schedule L exists with transaction data
  - Organization claims no interested person transactions but Schedule L is filed
  - Inconsistent reporting — suggests confusion about disclosure requirements or intentional concealment
  - SR-006

### Compensation Red Flags

- **Part VII Section A shows officer name with $0, $0, $0** (all compensation columns empty) combined with **gross receipts > $500K**
  - Large organization with unpaid leadership is suspicious
  - Officer may be compensated through related entities or hidden mechanisms
  - SR-013

- **Part VII compensation highly concentrated** (one officer = 80%+ of total compensation)
  - May indicate founder dependence or key person risk
  - Could signal salary inflation for single executive

- **Schedule J shows bonus/incentive compensation >> base compensation**
  - Suggests compensation is heavily discretionary
  - May not meet reasonableness test under IRC 4958

### Transaction Red Flags

- **Schedule L Part IV (business transactions)** shows large payments (> 10% of revenue) to insider-owned entities
  - Potential self-dealing
  - May not be at arm's length price

- **Schedule L Part III (grants)** shows grants to officers' relatives without clear program purpose
  - Potential excess benefit transaction
  - Violates IRC 4958

- **Schedule L Part II (loans)** shows ongoing loans to officers at below-market interest rates
  - Constitutes excess benefit
  - IRC 4947 violation

### Financial Red Flags

- **Part VIII revenue changes 50%+ year-over-year** with no corresponding change in program service activities (Part III)
  - Revenue increase not explained by program growth
  - Suggests one-time gift, acquisition, or accounting change rather than sustainable growth

- **Part IX shows funding imbalance** (e.g., 80% fundraising expense, 10% program expense)
  - Organization is spending more on fundraising than on mission
  - Violates charitable purpose doctrine

- **Part X shows negative net assets** (liabilities > assets)
  - Organization is technically insolvent
  - Sustainability risk

---

## Catalyst's Dependency on Accurate Form 990 Parsing

Every signal rule depends on correctly extracting and interpreting specific Form 990 fields:

- **SR-006**: Depends on Part IV Lines 28-29 and Schedule L presence being parsed accurately
- **SR-011**: Depends on Part VI Line 1b (count of independent members) being correct
- **SR-012**: Depends on Part VI Line 12a (Yes/No for COI policy) being correct
- **SR-013**: Depends on Part VII compensation table (names, titles, three compensation columns) being parsed correctly

If a parser returns the wrong line number, misinterprets a field, or confuses Part VI Line 1a (total members) with Line 1b (independent members), the signal rule will fire on incorrect data.

Your role as IRS Domain Expert is to catch these errors before Catalyst deploys a parser that creates false positives or misses real problems.

---

## References

- [IRS Form 990 Instructions (2025)](https://www.irs.gov/instructions/i990)
- [IRS Form 990 Parts and Schedules Overview](https://www.irs.gov/charities-non-profits/form-990-schedules-with-instructions)
- [Form 990 Part VI: Governance, Management, and Disclosure (IRS)](https://www.irs.gov/charities-non-profits/exempt-organizations-annual-reporting-requirements-governance-form-990-part-vi)
- [Form 990 Part VII and Schedule J: Compensation Information (IRS)](https://www.irs.gov/charities-non-profits/exempt-organizations-annual-reporting-requirements-form-990-part-vii-and-schedule-j-compensation-information)
- [Form 990 Schedule L: Transactions with Interested Persons (IRS)](https://www.irs.gov/charities-non-profits/form-990-filing-tips-schedule-l-transactions-with-interested-persons)
- [IRS Modernized e-File (MeF) XML Schemas](https://www.irs.gov/e-file-providers/modernized-e-file-mef-schemas-and-business-rules)
- [Form 990 XML Schema Documentation (IRS)](https://www.irs.gov/e-file-providers/current-valid-xml-schemas-and-business-rules-for-exempt-organizations-and-other-tax-exempt-entities-modernized-e-file)
