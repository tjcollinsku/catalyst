import { LegalCitation } from "../types";

/**
 * Maps signal rule_id → relevant legal citations.
 * Citations link to authoritative sources (Ohio Legislature, IRS, Cornell LII).
 */
export const SIGNAL_CITATIONS: Record<string, LegalCitation[]> = {
    "SR-001": [
        {
            code: "ORC \u00A71339.05",
            title: "Ohio Revised Code \u2014 Execution of Instruments by Deceased",
            url: "https://codes.ohio.gov/ohio-revised-code/section-1339.05",
        },
        {
            code: "ORC \u00A72913.42",
            title: "Ohio Revised Code \u2014 Tampering with Records / Forgery",
            url: "https://codes.ohio.gov/ohio-revised-code/section-2913.42",
        },
    ],
    "SR-002": [
        {
            code: "ORC \u00A72921.13",
            title: "Ohio Revised Code \u2014 Falsification in Official Matter",
            url: "https://codes.ohio.gov/ohio-revised-code/section-2921.13",
        },
        {
            code: "ORC \u00A74735.18",
            title: "Ohio Revised Code \u2014 Notary Public Misconduct",
            url: "https://codes.ohio.gov/ohio-revised-code/section-4735.18",
        },
    ],
    "SR-003": [
        {
            code: "IRC \u00A7170(h)",
            title: "Internal Revenue Code \u2014 Conservation Easement Deductions",
            url: "https://www.law.cornell.edu/uscode/text/26/170",
        },
        {
            code: "ORC \u00A71716.04",
            title: "Ohio Revised Code \u2014 Charitable Trust Supervision",
            url: "https://codes.ohio.gov/ohio-revised-code/section-1716.04",
        },
    ],
    "SR-004": [
        {
            code: "IRC \u00A76033",
            title: "Internal Revenue Code \u2014 Returns by Exempt Organizations",
            url: "https://www.law.cornell.edu/uscode/text/26/6033",
        },
    ],
    "SR-005": [
        {
            code: "IRC \u00A74941",
            title: "Internal Revenue Code \u2014 Taxes on Self-Dealing",
            url: "https://www.law.cornell.edu/uscode/text/26/4941",
        },
        {
            code: "ORC \u00A71702.30",
            title: "Ohio Revised Code \u2014 Fiduciary Duty of Directors",
            url: "https://codes.ohio.gov/ohio-revised-code/section-1702.30",
        },
    ],
    "SR-006": [
        {
            code: "ORC \u00A71309",
            title: "Ohio Revised Code \u2014 Secured Transactions (UCC Article 9)",
            url: "https://codes.ohio.gov/ohio-revised-code/chapter-1309",
        },
    ],
    "SR-007": [
        {
            code: "ORC \u00A7117.16",
            title: "Ohio Revised Code \u2014 Competitive Bidding Requirements",
            url: "https://codes.ohio.gov/ohio-revised-code/section-117.16",
        },
        {
            code: "2 CFR \u00A7200.320",
            title: "Code of Federal Regulations \u2014 Methods of Procurement",
            url: "https://www.law.cornell.edu/cfr/text/2/section-200.320",
        },
    ],
    "SR-008": [
        {
            code: "IRC \u00A76033",
            title: "Internal Revenue Code \u2014 Exempt Org Reporting",
            url: "https://www.law.cornell.edu/uscode/text/26/6033",
        },
        {
            code: "ORC \u00A71716.14",
            title: "Ohio Revised Code \u2014 Charitable Trust Reporting",
            url: "https://codes.ohio.gov/ohio-revised-code/section-1716.14",
        },
    ],
    "SR-009": [
        {
            code: "IRC \u00A7501(c)(3)",
            title: "Internal Revenue Code \u2014 Tax-Exempt Organizations",
            url: "https://www.law.cornell.edu/uscode/text/26/501",
        },
        {
            code: "ORC \u00A71716",
            title: "Ohio Revised Code \u2014 Charitable Trusts",
            url: "https://codes.ohio.gov/ohio-revised-code/chapter-1716",
        },
    ],
    "SR-010": [
        {
            code: "ORC \u00A71702.12",
            title: "Ohio Revised Code \u2014 Officer Requirements",
            url: "https://codes.ohio.gov/ohio-revised-code/section-1702.12",
        },
        {
            code: "IRC \u00A74958",
            title: "Internal Revenue Code \u2014 Excess Benefit Transactions",
            url: "https://www.law.cornell.edu/uscode/text/26/4958",
        },
    ],
};
