"""
Ohio County Recorder connector for Catalyst.

Strategy: human-in-the-loop document retrieval + structured parsing.

Why no scraper?
    Ohio's 88 county recorder offices use at least four different vendor systems
    (GovOS CountyFusion, GovOS Cloud Search, Laredo/Fidlar, USLandRecords), each
    with different session management, login flows, and anti-automation protections.
    Building a reliable scraper for all 88 counties would be brittle, legally
    questionable, and contrary to the Catalyst Principle: the human investigator
    is always the decision-maker.

What this connector DOES:
    1. URL Builder — given a county name and a search term (grantor/grantee name
       or parcel ID), generates the correct direct URL for that county's online
       recorder search portal. The investigator clicks the link, does the search,
       and downloads the document. Catalyst handles it from there.

    2. Document Parser — given the extracted text of a recorder document (deed,
       mortgage, UCC, etc.) already in the pipeline, parses structured fields:
       grantor(s), grantee(s), consideration amount, parcel ID, recording date,
       instrument type, legal description snippet, preparer/attorney.

    3. County Registry — a complete mapping of all 88 Ohio counties to their
       recorder portal URL, system vendor, and search tips.

Design principles:
    - No HTTP requests in the core module. All network I/O is intentional and
      triggered by the investigator, not the system.
    - Stateless: no Django imports, no DB writes.
    - Structured errors: RecorderError with a county attribute so the caller
      knows which county failed.
    - Human-in-the-loop by design: every county entry includes a note explaining
      what manual steps are needed for that system.

Investigative context (why this matters):
    The founding investigation centered on deeds recorded in Seneca County, Ohio.
    Key signals included:
    - Zero-consideration transfers between related parties (SR-005)
    - A deed naming a grantee LLC that did not exist until 2 years later (SR-002)
    - Repeated use of the same attorney with "without benefit of title search"
      disclaimers

    The county recorder data is where property ownership chains are documented.
    It is the ground truth for who owns what, when they got it, what they paid,
    and who prepared the documents.

Usage:
    from investigations.county_recorder_connector import (
        get_search_url,
        parse_recorder_document,
        get_county_info,
        list_counties,
        RecorderError,
        OhioCounty,
        RecorderSystem,
    )

    # Get the search URL for Seneca County
    url_info = get_search_url(OhioCounty.SENECA, grantor_grantee="HOMAN")
    print(url_info.url)
    print(url_info.instructions)

    # Parse a deed document already extracted by the pipeline
    doc = parse_recorder_document(extracted_text, county=OhioCounty.SENECA)
    print(doc.grantor, doc.grantee, doc.consideration, doc.parcel_id)

    # List all 88 counties
    for county in list_counties():
        info = get_county_info(county)
        print(info.name, info.system.value, info.portal_url)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class RecorderError(Exception):
    """
    Raised when the county recorder connector cannot complete an operation.

    Attributes:
        message: Human-readable description of what went wrong.
        county:  The OhioCounty enum value involved, if applicable.
    """

    def __init__(self, message: str, county: "OhioCounty | None" = None):
        super().__init__(message)
        self.county = county


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RecorderSystem(Enum):
    """
    The online search system used by a county recorder's office.

    Values represent the vendor/platform name. This determines how the URL
    builder constructs the search link and what manual steps are required.

    GOVOS_COUNTYFUSION:  Kofile/GovOS CountyFusion JSP app. Requires a
                          session — the investigator must log in as a guest
                          (free) before searching. URL opens the login page.

    GOVOS_CLOUD_SEARCH:  Newer GovOS Cloud Search (publicsearch.us). No login
                          required. Direct name search URL available.

    DTS_PAXWORLD:        Document Technology Systems (DTS) PAXWorld platform.
                          Ohio-based vendor. Counties either host on dts-oh.com
                          or on their own subdomain. No login required for public
                          index search. Confirmed working without VPN. Note:
                          Trumbull County migrated from CountyFusion to DTS
                          PAXWorld (contract signed May 2023).

    FIDLAR_AVA:          Fidlar Technologies AVA (Advanced Vanguard Access) web
                          platform. Successor to Laredo for many Ohio counties.
                          Free public index search at ava.fidlar.com or
                          rep*.laredo.fidlar.com subdomains. No login required
                          for index; images may require subscription.

    EAGLEWEB:            Tyler Technologies EagleWeb platform. County-hosted
                          at tylerhost.net or county subdomains. Free public
                          index search. No login required.

    COTT_SYSTEMS:        Cott Systems cloud-hosted platform (cotthosting.com).
                          Free public index search. No login required.

    LAREDO:              Fidlar Technologies Laredo (legacy). Subscription
                          required for remote access; some counties offer free
                          guest access. Many Ohio counties have migrated to
                          FIDLAR_AVA — check portal_notes.

    USLANDRECORDS:       Avenu Insights USLandRecords ohlr3 platform. Free
                          public access. County selected from dropdown.

    COMPILED_TECH:       Compiled Technologies IDX platform. Ohio-based vendor.
                          Counties hosted at {county}oh.compiled-technologies.com.
                          Full-featured interface: grantor/grantee, instrument type,
                          book/page, image links, date range filters. No login
                          required for public index. Confirmed working: Meigs,
                          Crawford. Knox has a certificate error — verify separately.

    CUSTOM:              County-hosted or other vendor. URL provided directly;
                          check portal_notes for access details.

    UNAVAILABLE:         No online search available. In-person visit required.
    """
    GOVOS_COUNTYFUSION = "GovOS CountyFusion"
    GOVOS_CLOUD_SEARCH = "GovOS Cloud Search"
    DTS_PAXWORLD = "DTS PAXWorld"
    FIDLAR_AVA = "Fidlar AVA"
    EAGLEWEB = "EagleWeb (Tyler)"
    COTT_SYSTEMS = "Cott Systems"
    COMPILED_TECH = "Compiled Technologies"
    LAREDO = "Laredo (Fidlar)"
    USLANDRECORDS = "USLandRecords (Avenu)"
    CUSTOM = "Custom/Other"
    UNAVAILABLE = "In-Person Only"


# ---------------------------------------------------------------------------
# County registry
# ---------------------------------------------------------------------------

@dataclass
class CountyInfo:
    """
    All metadata about a single Ohio county's recorder system.

    Attributes:
        name:           County name (e.g., "Seneca").
        fips:           Ohio county FIPS code (001–175, odd numbers only).
        seat:           County seat city.
        system:         RecorderSystem enum — which vendor platform.
        portal_url:     Direct URL to the recorder's online search portal.
                        For GOVOS_COUNTYFUSION this is the login/entry page.
                        For GOVOS_CLOUD_SEARCH this opens the search directly.
                        None if UNAVAILABLE.
        search_url_template: URL template for name searches. Use {name} as
                        placeholder for the search term. None if not applicable.
        portal_notes:   Plain-English instructions for the investigator on how
                        to use this county's system.
        phone:          Recorder's office phone number.
        address:        Physical address of the recorder's office.
        records_from:   Earliest year of online records (None if unknown).
    """
    name: str
    fips: str
    seat: str
    system: RecorderSystem
    portal_url: str | None
    search_url_template: str | None
    portal_notes: str
    phone: str
    address: str
    records_from: int | None = None


@dataclass
class SearchUrlResult:
    """
    Returned by get_search_url(). Contains the URL and investigator instructions.

    Attributes:
        county:       The OhioCounty enum value.
        county_name:  Human-readable county name.
        url:          The URL to open in a browser. For GOVOS_COUNTYFUSION this
                      is the login page (guest access is free). For
                      GOVOS_CLOUD_SEARCH this may be a direct search URL.
        system:       Which vendor platform this county uses.
        instructions: Plain-English steps for the investigator.
        requires_login: True if the system requires a login/guest session before
                        searching. The investigator must complete this manually.
    """
    county: "OhioCounty"
    county_name: str
    url: str | None
    system: RecorderSystem
    instructions: str
    requires_login: bool


# ---------------------------------------------------------------------------
# Parsed document structure
# ---------------------------------------------------------------------------

@dataclass
class RecorderDocument:
    """
    Structured data parsed from a recorder document's extracted text.

    All fields are Optional — not all document types contain all fields,
    and OCR quality varies. The caller should validate before using in signals.

    Attributes:
        instrument_type:     "DEED", "MORTGAGE", "UCC", "RELEASE", "EASEMENT",
                             "SATISFACTION", "AFFIDAVIT", "OTHER", or None.
        grantor:             Primary grantor name (seller / borrower).
        grantors:            All grantor names found in the document.
        grantee:             Primary grantee name (buyer / lender).
        grantees:            All grantee names found in the document.
        consideration:       Dollar amount of consideration/purchase price.
                             0.0 for zero-consideration transfers.
        consideration_text:  Raw consideration text as found in document
                             (e.g., "TEN DOLLARS AND OTHER VALUABLE CONSIDERATION").
        parcel_id:           County parcel identification number.
        legal_description:   First 500 chars of legal description, if found.
        recording_date:      Date document was recorded (not executed).
        instrument_number:   Recorder's instrument/document number.
        book_page:           Book and page reference (e.g., "Book 245 Page 12").
        preparer:            Attorney or preparer name, if found.
        preparer_notes:      Any preparer disclaimer text (e.g., "without
                             benefit of title search" — investigatively significant).
        county:              Ohio county where document was recorded.
        raw_text_snippet:    First 1000 chars of the extracted text, for audit.
    """
    instrument_type: str | None = None
    grantor: str | None = None
    grantors: list[str] = field(default_factory=list)
    grantee: str | None = None
    grantees: list[str] = field(default_factory=list)
    consideration: float | None = None
    consideration_text: str | None = None
    parcel_id: str | None = None
    legal_description: str | None = None
    recording_date: str | None = None
    instrument_number: str | None = None
    book_page: str | None = None
    preparer: str | None = None
    preparer_notes: str | None = None
    county: "OhioCounty | None" = None
    raw_text_snippet: str | None = None


# ---------------------------------------------------------------------------
# Ohio County enum — all 88 counties
# ---------------------------------------------------------------------------

class OhioCounty(Enum):
    """
    All 88 Ohio counties by name.

    Values are lowercase slugs used as keys in the registry.
    """
    ADAMS = "adams"
    ALLEN = "allen"
    ASHLAND = "ashland"
    ASHTABULA = "ashtabula"
    ATHENS = "athens"
    AUGLAIZE = "auglaize"
    BELMONT = "belmont"
    BROWN = "brown"
    BUTLER = "butler"
    CARROLL = "carroll"
    CHAMPAIGN = "champaign"
    CLARK = "clark"
    CLERMONT = "clermont"
    CLINTON = "clinton"
    COLUMBIANA = "columbiana"
    COSHOCTON = "coshocton"
    CRAWFORD = "crawford"
    CUYAHOGA = "cuyahoga"
    DARKE = "darke"
    DEFIANCE = "defiance"
    DELAWARE = "delaware"
    ERIE = "erie"
    FAIRFIELD = "fairfield"
    FAYETTE = "fayette"
    FRANKLIN = "franklin"
    FULTON = "fulton"
    GALLIA = "gallia"
    GEAUGA = "geauga"
    GREENE = "greene"
    GUERNSEY = "guernsey"
    HAMILTON = "hamilton"
    HANCOCK = "hancock"
    HARDIN = "hardin"
    HARRISON = "harrison"
    HENRY = "henry"
    HIGHLAND = "highland"
    HOCKING = "hocking"
    HOLMES = "holmes"
    HURON = "huron"
    JACKSON = "jackson"
    JEFFERSON = "jefferson"
    KNOX = "knox"
    LAKE = "lake"
    LAWRENCE = "lawrence"
    LICKING = "licking"
    LOGAN = "logan"
    LORAIN = "lorain"
    LUCAS = "lucas"
    MADISON = "madison"
    MAHONING = "mahoning"
    MARION = "marion"
    MEDINA = "medina"
    MEIGS = "meigs"
    MERCER = "mercer"
    MIAMI = "miami"
    MONROE = "monroe"
    MONTGOMERY = "montgomery"
    MORGAN = "morgan"
    MORROW = "morrow"
    MUSKINGUM = "muskingum"
    NOBLE = "noble"
    OTTAWA = "ottawa"
    PAULDING = "paulding"
    PERRY = "perry"
    PICKAWAY = "pickaway"
    PIKE = "pike"
    PORTAGE = "portage"
    PREBLE = "preble"
    PUTNAM = "putnam"
    RICHLAND = "richland"
    ROSS = "ross"
    SANDUSKY = "sandusky"
    SCIOTO = "scioto"
    SENECA = "seneca"
    SHELBY = "shelby"
    STARK = "stark"
    SUMMIT = "summit"
    TRUMBULL = "trumbull"
    TUSCARAWAS = "tuscarawas"
    UNION = "union"
    VAN_WERT = "van_wert"
    VINTON = "vinton"
    WARREN = "warren"
    WASHINGTON = "washington"
    WAYNE = "wayne"
    WILLIAMS = "williams"
    WOOD = "wood"
    WYANDOT = "wyandot"


# ---------------------------------------------------------------------------
# County registry — all 88 Ohio counties
#
# Sources verified:
#   - Individual county recorder office websites
#   - GovOS blog posts (govos.com/blog/) for Cloud Search deployments
#   - Fidlar Technologies county list for Laredo
#   - USLandRecords ohlr3 county selector
#   - Ohio Recorders' Association (ohiorecorders.com) for contact info
#
# NOTE: Recorder system assignments are accurate as of early 2026 but may
# change. When in doubt, check the county's official website.
# ---------------------------------------------------------------------------

_REGISTRY: dict[OhioCounty, CountyInfo] = {

    OhioCounty.ADAMS: CountyInfo(
        name="Adams", fips="001", seat="West Union",
        system=RecorderSystem.CUSTOM,
        portal_url="https://adamscountyoh.gov/recorder/",
        search_url_template=None,
        portal_notes="Adams County uses a local search portal independent of major vendor platforms. No login required. Verified working.",
        phone="937-544-2364", address="110 W Main St, West Union, OH 45693",
        records_from=1987,
    ),
    OhioCounty.ALLEN: CountyInfo(
        name="Allen", fips="003", seat="Lima",
        system=RecorderSystem.DTS_PAXWORLD,
        portal_url="https://recorderexternal.allencountyohio.com/paxworld/",
        search_url_template=None,
        portal_notes="Allen County uses DTS PAXWorld hosted on county infrastructure. No login required. Search by grantor/grantee name, last name first. Confirmed accessible without VPN.",
        phone="419-228-3700", address="301 N Main St, Lima, OH 45801",
        records_from=1987,
    ),
    OhioCounty.ASHLAND: CountyInfo(
        name="Ashland", fips="005", seat="Ashland",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=AshlandOH",
        search_url_template=None,
        portal_notes="Ashland County uses legacy CountyFusion (kofiletech.us domain). Guest access. Search by grantor/grantee last name first. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="419-282-4235", address="142 W 2nd St, Ashland, OH 44805",
        records_from=1987,
    ),
    OhioCounty.ASHTABULA: CountyInfo(
        name="Ashtabula", fips="007", seat="Jefferson",
        system=RecorderSystem.COTT_SYSTEMS,
        portal_url="https://cotthosting.com/ohashtabula/User/Login.aspx",
        search_url_template=None,
        portal_notes="Ashtabula County uses Cott Systems cloud platform. Not affected by GovOS outage. Free public access. Verified working.",
        phone="440-576-3789", address="25 W Jefferson St, Jefferson, OH 44047",
        records_from=1987,
    ),
    OhioCounty.ATHENS: CountyInfo(
        name="Athens", fips="009", seat="Athens",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohathens.fidlar.com/OHAthens/AvaWeb/",
        search_url_template=None,
        portal_notes="Athens County migrated to Fidlar AVA. Free public index search. No login required. Verified working.",
        phone="740-592-3242", address="15 S Court St, Athens, OH 45701",
        records_from=1987,
    ),
    OhioCounty.AUGLAIZE: CountyInfo(
        name="Auglaize", fips="011", seat="Wapakoneta",
        system=RecorderSystem.CUSTOM,
        portal_url="http://gis.auglaizecounty.org/scanneddrawings/",
        search_url_template=None,
        portal_notes="Auglaize County uses a custom GIS/Scanned Drawings portal for public record access. Not a standard vendor platform. Verified working.",
        phone="419-738-3612", address="201 Willipie St, Wapakoneta, OH 45895",
        records_from=1987,
    ),
    OhioCounty.BELMONT: CountyInfo(
        name="Belmont", fips="013", seat="St. Clairsville",
        system=RecorderSystem.CUSTOM,
        portal_url="https://belmontcountyrecorder.org/",
        search_url_template=None,
        portal_notes="Belmont County uses a new custom site independent of major vendor platforms. Verified working.",
        phone="740-695-2121", address="101 W Main St, St. Clairsville, OH 43950",
        records_from=1987,
    ),
    OhioCounty.BROWN: CountyInfo(
        name="Brown", fips="015", seat="Georgetown",
        system=RecorderSystem.CUSTOM,
        portal_url="https://www.browncountyohio.gov/index.php/recorder44",
        search_url_template=None,
        portal_notes="Brown County uses a custom county portal. Verified working and stable.",
        phone="937-378-3956", address="800 Mt Orab Pike, Georgetown, OH 45121",
        records_from=1987,
    ),
    OhioCounty.BUTLER: CountyInfo(
        name="Butler", fips="017", seat="Hamilton",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://butler.oh.publicsearch.us/",
        search_url_template="https://butler.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Butler County uses GovOS Cloud Search (publicsearch.us). No login required. Verified working and independent of CF outage.",
        phone="513-887-3192", address="130 High St, Hamilton, OH 45011",
        records_from=1985,
    ),
    OhioCounty.CARROLL: CountyInfo(
        name="Carroll", fips="019", seat="Carrollton",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://carroll.oh.publicsearch.us/",
        search_url_template="https://carroll.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="GovOS Cloud Search — no login required. Enter name directly in the search box. Results include instrument type, date, and parties.",
        phone="330-627-2250", address="119 S Lisbon St, Carrollton, OH 44615",
        records_from=1818,
    ),
    OhioCounty.CHAMPAIGN: CountyInfo(
        name="Champaign", fips="021", seat="Urbana",
        system=RecorderSystem.CUSTOM,
        portal_url="https://champaigncountyrecorder.us/",
        search_url_template=None,
        portal_notes=(
            "Champaign County uses a Tapestry Eon system (NOT Fidlar AVA as previously listed). "
            "Free public index search. No login required. "
            "⚠️ URL CORRECTED 2026-03-28: previous ava.fidlar.com URL returned HTTP 404. "
            "Official site champaigncountyrecorder.us confirmed via county government path."
        ),
        phone="937-484-1627", address="200 N Main St, Urbana, OH 43078",
        records_from=1987,
    ),
    OhioCounty.CLARK: CountyInfo(
        name="Clark", fips="023", seat="Springfield",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://clark.oh.publicsearch.us/",
        search_url_template="https://clark.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="GovOS Cloud Search — no login required. Records dating back to 1818.",
        phone="937-521-1680", address="31 N Limestone St, Springfield, OH 45502",
        records_from=1818,
    ),
    OhioCounty.CLERMONT: CountyInfo(
        name="Clermont", fips="025", seat="Batavia",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://clermontoh-recorder.govos.com/",
        search_url_template=None,
        portal_notes="Clermont County uses GovOS CountyFusion on a dedicated county subdomain. Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="513-732-7243", address="101 E Main St, Batavia, OH 45103",
        records_from=1987,
    ),
    OhioCounty.CLINTON: CountyInfo(
        name="Clinton", fips="027", seat="Wilmington",
        system=RecorderSystem.CUSTOM,
        portal_url="https://co.clinton.oh.us/ClintonCountyRecordersOnlineRecordsSystem",
        search_url_template=None,
        portal_notes="Clinton County hosts its own records search portal via the county website. No login required for public index. Verify URL is current — county website links here from the Recorder page.",
        phone="937-382-2316", address="46 S South St, Wilmington, OH 45177",
        records_from=1987,
    ),
    OhioCounty.COLUMBIANA: CountyInfo(
        name="Columbiana", fips="029", seat="Lisbon",
        system=RecorderSystem.CUSTOM,
        portal_url="https://www.columbianacountyrecorder.org/",
        search_url_template=None,
        portal_notes="Columbiana County uses an independent web database. Not a standard vendor platform. Verified working.",
        phone="330-424-9515", address="105 S Market St, Lisbon, OH 44432",
        records_from=1987,
    ),
    OhioCounty.COSHOCTON: CountyInfo(
        name="Coshocton", fips="031", seat="Coshocton",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion1.kofiletech.us/",
        search_url_template=None,
        portal_notes="Coshocton County uses legacy CountyFusion (kofiletech.us domain). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="740-622-1766", address="349 Main St, Coshocton, OH 43812",
        records_from=1987,
    ),
    OhioCounty.CRAWFORD: CountyInfo(
        name="Crawford", fips="033", seat="Bucyrus",
        system=RecorderSystem.COMPILED_TECH,
        portal_url="https://crawfordoh.compiled-technologies.com/Default.aspx",
        search_url_template=None,
        portal_notes="Crawford County uses Compiled Technologies IDX platform (same as Meigs). URL confirmed via web search 2026-03-28. Prior URL (crawfordohrecorder.com) was a redirect — this is the actual search portal. No login required.",
        phone="419-562-2766", address="112 E Mansfield St, Bucyrus, OH 44820",
        records_from=1987,
    ),
    OhioCounty.CUYAHOGA: CountyInfo(
        name="Cuyahoga", fips="035", seat="Cleveland",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://cuyahoga.oh.publicsearch.us/",
        search_url_template="https://cuyahoga.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Cuyahoga County uses GovOS Cloud Search. Records from 1810 to present. No login required. Verified working and independent of CF outage.",
        phone="216-443-7300", address="2079 E 9th St, Cleveland, OH 44115",
        records_from=1980,
    ),
    OhioCounty.DARKE: CountyInfo(
        name="Darke", fips="037", seat="Greenville",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://rep2laredo.fidlar.com/OHDarke/AvaWeb/",
        search_url_template=None,
        portal_notes="Darke County migrated to Fidlar AVA. Free public index search. No login required. Verified working. Key county for Osgood investigation.",
        phone="937-547-7360", address="300 Garst Ave, Greenville, OH 45331",
        records_from=1987,
    ),
    OhioCounty.DEFIANCE: CountyInfo(
        name="Defiance", fips="039", seat="Defiance",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://defiance-county.com/recorder/index.php",
        search_url_template=None,
        portal_notes="Defiance County confirmed on Fidlar AVA (index search via county website). Verified working.",
        phone="419-782-4761", address="221 Clinton St, Defiance, OH 43512",
        records_from=1987,
    ),
    OhioCounty.DELAWARE: CountyInfo(
        name="Delaware", fips="041", seat="Delaware",
        system=RecorderSystem.CUSTOM,
        portal_url="https://recorder.co.delaware.oh.us/records-search-page/",
        search_url_template=None,
        portal_notes="Delaware County has its own search portal. Free public access for grantor/grantee name searches.",
        phone="740-833-2350", address="91 N Sandusky St, Delaware, OH 43015",
        records_from=1987,
    ),
    OhioCounty.ERIE: CountyInfo(
        name="Erie", fips="043", seat="Sandusky",
        system=RecorderSystem.EAGLEWEB,
        portal_url="https://eriecountyoh-selfservice.tylerhost.net/web/",
        search_url_template=None,
        portal_notes="Erie County uses Tyler Technologies EagleWeb (tylerhost.net). Free public index search. No login required. Verified working.",
        phone="419-627-7686", address="323 Columbus Ave, Sandusky, OH 44870",
        records_from=1987,
    ),
    OhioCounty.FAIRFIELD: CountyInfo(
        name="Fairfield", fips="045", seat="Lancaster",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ava.fidlar.com/OHFairfield/AvaWeb/",
        search_url_template=None,
        portal_notes="Fairfield County uses Fidlar AVA (includes legacy deed index). Verified working.",
        phone="740-687-7030", address="210 E Main St, Lancaster, OH 43130",
        records_from=1987,
    ),
    OhioCounty.FAYETTE: CountyInfo(
        name="Fayette", fips="047", seat="Washington Court House",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=FayetteOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-335-0440", address="110 E Court St, Washington Court House, OH 43160",
        records_from=1987,
    ),
    OhioCounty.FRANKLIN: CountyInfo(
        name="Franklin", fips="049", seat="Columbus",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://franklin.oh.publicsearch.us/",
        search_url_template="https://franklin.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Franklin County uses GovOS Cloud Search. Free public access. Records from 1800s. Verified working.",
        phone="614-525-3930", address="373 S High St, Columbus, OH 43215",
        records_from=1800,
    ),
    OhioCounty.FULTON: CountyInfo(
        name="Fulton", fips="051", seat="Wauseon",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=FultonOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="419-337-9232", address="152 S Fulton St, Wauseon, OH 43567",
        records_from=1987,
    ),
    OhioCounty.GALLIA: CountyInfo(
        name="Gallia", fips="053", seat="Gallipolis",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=GalliaOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-446-4612", address="18 Locust St, Gallipolis, OH 45631",
        records_from=1987,
    ),
    OhioCounty.GEAUGA: CountyInfo(
        name="Geauga", fips="055", seat="Chardon",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ava.fidlar.com/OHGeauga/AvaWeb/",
        search_url_template=None,
        portal_notes="Geauga County migrated to Fidlar AVA. Verified working.",
        phone="440-285-2222", address="231 Main St, Chardon, OH 44024",
        records_from=1987,
    ),
    OhioCounty.GREENE: CountyInfo(
        name="Greene", fips="057", seat="Xenia",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://greene.oh.publicsearch.us/",
        search_url_template="https://greene.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Greene County uses GovOS Cloud Search. Verified working.",
        phone="937-562-5270", address="45 N Detroit St, Xenia, OH 45385",
        records_from=1987,
    ),
    OhioCounty.GUERNSEY: CountyInfo(
        name="Guernsey", fips="059", seat="Cambridge",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion9.kofiletech.us/countyweb/loginDisplay.action?countyname=GuernseyOH",
        search_url_template=None,
        portal_notes="Guernsey County uses legacy CountyFusion (kofiletech.us domain). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="740-432-9270", address="627 Wheeling Ave, Cambridge, OH 43725",
        records_from=1987,
    ),
    OhioCounty.HAMILTON: CountyInfo(
        name="Hamilton", fips="061", seat="Cincinnati",
        system=RecorderSystem.CUSTOM,
        portal_url="https://acclaim-web.hamiltoncountyohio.gov/AcclaimWebLive/",
        search_url_template=None,
        portal_notes="Hamilton County uses Acclaim-Web (custom system). Unaffected by GovOS outage. Verified working.",
        phone="513-946-4570", address="138 E Court St, Cincinnati, OH 45202",
        records_from=1987,
    ),
    OhioCounty.HANCOCK: CountyInfo(
        name="Hancock", fips="063", seat="Findlay",
        system=RecorderSystem.CUSTOM,
        portal_url="https://www.co.hancock.oh.us/196/Record-Search",
        search_url_template=None,
        portal_notes=(
            "Hancock County uses a custom county portal. Index available 1985–present. "
            "Search by name, instrument number, book/page, subdivision, township, or condo. "
            "Parcel number searches NOT supported in the Recorder's system. "
            "⚠️ URL CORRECTED 2026-03-28: previous recorder.co.hancock.oh.us returned connection error."
        ),
        phone="419-424-7091", address="300 S Main St Room 23, Findlay, OH 45840",
        records_from=1985,
    ),
    OhioCounty.HARDIN: CountyInfo(
        name="Hardin", fips="065", seat="Kenton",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=HardinOH",
        search_url_template=None,
        portal_notes="Hardin County uses legacy CountyFusion (kofiletech.us domain). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="419-674-2246", address="One Courthouse Square, Kenton, OH 43326",
        records_from=1987,
    ),
    OhioCounty.HARRISON: CountyInfo(
        name="Harrison", fips="067", seat="Cadiz",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://harrison.oh.publicsearch.us/",
        search_url_template="https://harrison.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Harrison County migrated to GovOS Cloud Search. Images from 2008–present. Verified working.",
        phone="740-942-8861", address="100 W Market St, Cadiz, OH 43907",
        records_from=1987,
    ),
    OhioCounty.HENRY: CountyInfo(
        name="Henry", fips="069", seat="Napoleon",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HenryOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="419-592-4876", address="660 State Rt 424, Napoleon, OH 43545",
        records_from=1987,
    ),
    OhioCounty.HIGHLAND: CountyInfo(
        name="Highland", fips="071", seat="Hillsboro",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HighlandOH",
        search_url_template=None,
        portal_notes=(
            "Guest access available. Search by grantor/grantee last name first. "
            "Highland County actively promotes GovOS FraudSleuth — a free property "
            "fraud alert feature where residents register their name and receive email "
            "notification when a document is recorded in their name. Investigative note: "
            "subjects with FraudSleuth active may become aware of new recordings quickly."
        ),
        phone="937-393-9954", address="105 N High St, Hillsboro, OH 45133",
        records_from=1987,
    ),
    OhioCounty.HOCKING: CountyInfo(
        name="Hocking", fips="073", seat="Logan",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HockingOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-385-2127", address="1 E Main St, Logan, OH 43138",
        records_from=1987,
    ),
    OhioCounty.HOLMES: CountyInfo(
        name="Holmes", fips="075", seat="Millersburg",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohholmes.fidlar.com/OHHolmes/AvaWeb/",
        search_url_template=None,
        portal_notes="Holmes County uses Fidlar AVA (county-specific subdomain). Free public index search. Document images may require subscription. URL confirmed via official county site 2026-03-28.",
        phone="330-674-1876", address="1 E Jackson St, Millersburg, OH 44654",
        records_from=1987,
    ),
    OhioCounty.HURON: CountyInfo(
        name="Huron", fips="077", seat="Norwalk",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=HuronOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="419-668-5113", address="2 Courthouse Square, Norwalk, OH 44857",
        records_from=1987,
    ),
    OhioCounty.JACKSON: CountyInfo(
        name="Jackson", fips="079", seat="Jackson",
        system=RecorderSystem.CUSTOM,
        portal_url="https://www.jacksoncountyohio.us/elected-officials/recorder/",
        search_url_template=None,
        portal_notes="Jackson County uses a custom county portal. Registration required for document images. Verified working.",
        phone="740-286-4591", address="226 E Main St, Jackson, OH 45640",
        records_from=1987,
    ),
    OhioCounty.JEFFERSON: CountyInfo(
        name="Jefferson", fips="081", seat="Steubenville",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://jefferson.oh.publicsearch.us/",
        search_url_template="https://jefferson.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Jefferson County migrated to GovOS Cloud Search. Images from 2008–present. Verified working.",
        phone="740-283-8572", address="301 Market St, Steubenville, OH 43952",
        records_from=1987,
    ),
    OhioCounty.KNOX: CountyInfo(
        name="Knox", fips="083", seat="Mount Vernon",
        system=RecorderSystem.COTT_SYSTEMS,
        portal_url="https://cotthosting.com/OHKnoxLANExternal/LandRecords/protected/v4/SrchName.aspx",
        search_url_template=None,
        portal_notes=(
            "Knox County uses Cott Systems (cotthosting.com/OHKnoxLANExternal). "
            "Free public index search — grantor/grantee name, instrument type, book/page. "
            "⚠️ URL CORRECTED 2026-03-28: previous knoxoh.compiled-technologies.com had "
            "an invalid/expired TLS certificate. Switched to Cott Systems alternative."
        ),
        phone="740-393-6788", address="117 E High St, Mount Vernon, OH 43050",
        records_from=1987,
    ),
    OhioCounty.LAKE: CountyInfo(
        name="Lake", fips="085", seat="Painesville",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://rep2laredo.fidlar.com/OHLake/AvaWeb/#/search",
        search_url_template=None,
        portal_notes="Lake County uses Fidlar AVA (rep2laredo subdomain) for free public index search — grantor/grantee, instrument type, book/page. Index available from 1986. No login required for index. "
                     "NOTE: Document IMAGES require a separate Laredo Select account (paid subscription) — form at lakecountyohiorecorder.com. "
                     "Prior URL (ava.fidlar.com/OHLake/AvaWeb/) was stale — corrected to rep2laredo instance confirmed by user 2026-03-28.",
        phone="440-350-2519", address="105 Main St, Painesville, OH 44077",
        records_from=1986,
    ),
    OhioCounty.LAWRENCE: CountyInfo(
        name="Lawrence", fips="087", seat="Ironton",
        system=RecorderSystem.COTT_SYSTEMS,
        portal_url="https://cotthosting.com/OHLawrenceExternal/LandRecords/protected/v4/SrchName.aspx",
        search_url_template=None,
        portal_notes="Lawrence County uses Cott Systems. Not affected by GovOS outage. Verified working.",
        phone="740-533-4354", address="111 S 4th St, Ironton, OH 45638",
        records_from=1987,
    ),
    OhioCounty.LICKING: CountyInfo(
        name="Licking", fips="089", seat="Newark",
        system=RecorderSystem.DTS_PAXWORLD,
        portal_url="https://apps.lickingcounty.gov/recorder/paxworld/",
        search_url_template=None,
        portal_notes="Licking County uses DTS PAXWorld hosted on county infrastructure. No login required. Search by grantor/grantee name, last name first.",
        phone="740-670-5110", address="20 S 2nd St, Newark, OH 43055",
        records_from=1987,
    ),
    OhioCounty.LOGAN: CountyInfo(
        name="Logan", fips="091", seat="Bellefontaine",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=LoganOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="937-599-7209", address="101 S Main St, Bellefontaine, OH 43311",
        records_from=1987,
    ),
    OhioCounty.LORAIN: CountyInfo(
        name="Lorain", fips="093", seat="Elyria",
        system=RecorderSystem.DTS_PAXWORLD,
        portal_url="https://recorder.dts-oh-lorain.com/paxworld/",
        search_url_template=None,
        portal_notes="Lorain County uses DTS PAXWorld on a dedicated DTS subdomain. No login required. Search by grantor/grantee name, last name first.",
        phone="440-329-5148", address="226 Middle Ave, Elyria, OH 44035",
        records_from=1987,
    ),
    OhioCounty.LUCAS: CountyInfo(
        name="Lucas", fips="095", seat="Toledo",
        system=RecorderSystem.DTS_PAXWORLD,
        portal_url="https://lucas.dts-oh.com/PaxWorld5/",
        search_url_template=None,
        portal_notes="Lucas County uses DTS PAXWorld5 (newer version). No login required. Search by grantor/grantee name, last name first.",
        phone="419-213-4400", address="One Government Center, Toledo, OH 43604",
        records_from=1987,
    ),
    OhioCounty.MADISON: CountyInfo(
        name="Madison", fips="097", seat="London",
        system=RecorderSystem.USLANDRECORDS,
        portal_url="https://madisonoh.avenuinsights.com/Home/index.html",
        search_url_template=None,
        portal_notes="⚠️ REQUIRES REGISTRATION — Madison County uses Avenu Insights platform but requires the investigator to register for a free account before searching. Landing page confirmed 2026-03-28 by user. Click 'Search Land Records' → 'Sign Up' to register. Recorder: Rachel Fisher. Phone corrected from 740-852-9717 to 740-852-1854 per landing page.",
        phone="740-852-1854", address="1 N Main St Room 40, London, OH 43140",
        records_from=1987,
    ),
    OhioCounty.MAHONING: CountyInfo(
        name="Mahoning", fips="099", seat="Youngstown",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MahoningOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="330-740-2061", address="120 Market St, Youngstown, OH 44503",
        records_from=1987,
    ),
    OhioCounty.MARION: CountyInfo(
        name="Marion", fips="101", seat="Marion",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://rep3laredo.fidlar.com/OHMarion/AvaWeb/",
        search_url_template=None,
        portal_notes="Marion County uses Fidlar AVA (rep3laredo subdomain). Free public index search. URL confirmed 2026-03-28 — previous ava.fidlar.com URL returned HTTP 404.",
        phone="740-223-4270", address="222 W Center St, Marion, OH 43302",
        records_from=1987,
    ),
    OhioCounty.MEDINA: CountyInfo(
        name="Medina", fips="103", seat="Medina",
        system=RecorderSystem.CUSTOM,
        portal_url="https://recorder.co.medina.oh.us/",
        search_url_template=None,
        portal_notes="Medina County uses a custom county-hosted portal. Not affected by platform outages. Verified working.",
        phone="330-725-9754", address="144 N Broadway St, Medina, OH 44256",
        records_from=1987,
    ),
    OhioCounty.MEIGS: CountyInfo(
        name="Meigs", fips="105", seat="Pomeroy",
        system=RecorderSystem.COMPILED_TECH,
        portal_url="https://meigsoh.compiled-technologies.com/Default.aspx",
        search_url_template=None,
        portal_notes="Meigs County uses Compiled Technologies IDX platform. Full-featured: grantor/grantee name search, instrument type filter, book/page, image links, date range. No login required. Records from 1994. Confirmed working and functional by user 2026-03-28.",
        phone="740-992-5290", address="100 E 2nd St, Pomeroy, OH 45769",
        records_from=1994,
    ),
    OhioCounty.MERCER: CountyInfo(
        name="Mercer", fips="107", seat="Celina",
        system=RecorderSystem.CUSTOM,
        portal_url="https://recorder.mercercountyoh.gov/LandmarkWeb/",
        search_url_template=None,
        portal_notes=(
            "Mercer County uses LandmarkWeb (not Fidlar AVA as previously listed). "
            "Free public index search — no login required. "
            "KEY COUNTY: Central to the Osgood investigation — grantor/grantee "
            "searches here critical for deed chain analysis. "
            "⚠️ URL CORRECTED 2026-03-28: previous ava.fidlar.com URL returned HTTP 404. "
            "Updated again to recorder.mercercountyoh.gov/LandmarkWeb based on direct user confirmation."
        ),
        phone="419-586-6402", address="101 N Main St, Celina, OH 45822",
        records_from=1987,
    ),
    OhioCounty.MIAMI: CountyInfo(
        name="Miami", fips="109", seat="Troy",
        system=RecorderSystem.LAREDO,
        portal_url="https://rep4laredo.fidlar.com/OHMiami/DirectSearch/#/search",
        search_url_template=None,
        portal_notes="Miami County migrated from Fidlar AVA to Fidlar Laredo (rep4laredo.fidlar.com). Direct name search available without login at the portal URL. Documents from 1998-present by name; 1980-1998 by book/page only. For in-depth remote access email recorder@miamicountyohio.gov. Confirmed working 2026-03-28. NOTE: Prior AVA URL (ava.fidlar.com/OHMiami/AvaWeb/) returns 404.",
        phone="937-440-6040", address="201 W Main St, Troy, OH 45373",
        records_from=1980,
    ),
    OhioCounty.MONROE: CountyInfo(
        name="Monroe", fips="111", seat="Woodsfield",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MonroeOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-472-0873", address="101 N Main St, Woodsfield, OH 43793",
        records_from=1987,
    ),
    OhioCounty.MONTGOMERY: CountyInfo(
        name="Montgomery", fips="113", seat="Dayton",
        system=RecorderSystem.CUSTOM,
        portal_url="https://riss.mcrecorder.org/",
        search_url_template=None,
        portal_notes="Montgomery County uses RISS (Regional Information Systems) portal. Stable and independent of vendor outages. Verified working.",
        phone="937-496-6670", address="451 W Third St, Dayton, OH 45422",
        records_from=1987,
    ),
    OhioCounty.MORGAN: CountyInfo(
        name="Morgan", fips="115", seat="McConnelsville",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MorganOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-962-4475", address="19 E Main St, McConnelsville, OH 43756",
        records_from=1987,
    ),
    OhioCounty.MORROW: CountyInfo(
        name="Morrow", fips="117", seat="Mount Gilead",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MorrowOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="419-947-4085", address="48 E High St, Mount Gilead, OH 43338",
        records_from=1987,
    ),
    OhioCounty.MUSKINGUM: CountyInfo(
        name="Muskingum", fips="119", seat="Zanesville",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=MuskingumOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-455-7109", address="401 Main St, Zanesville, OH 43701",
        records_from=1987,
    ),
    OhioCounty.NOBLE: CountyInfo(
        name="Noble", fips="121", seat="Caldwell",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=NobleOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-732-4045", address="260 Courthouse, Caldwell, OH 43724",
        records_from=1987,
    ),
    OhioCounty.OTTAWA: CountyInfo(
        name="Ottawa", fips="123", seat="Port Clinton",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://ottawa.oh.publicsearch.us/",
        search_url_template="https://ottawa.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Ottawa was the first Ohio county to launch GovOS Cloud Search. No login required.",
        phone="419-734-6740", address="315 Madison St, Port Clinton, OH 43452",
        records_from=1987,
    ),
    OhioCounty.PAULDING: CountyInfo(
        name="Paulding", fips="125", seat="Paulding",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ava.fidlar.com/OHPaulding/AvaWeb/",
        search_url_template=None,
        portal_notes="Paulding County uses Fidlar AVA. Verified working.",
        phone="419-399-8215", address="115 N Williams St, Paulding, OH 45879",
        records_from=1987,
    ),
    OhioCounty.PERRY: CountyInfo(
        name="Perry", fips="127", seat="New Lexington",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=PerryOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="740-342-1508", address="121 W Brown St, New Lexington, OH 43764",
        records_from=1987,
    ),
    OhioCounty.PICKAWAY: CountyInfo(
        name="Pickaway", fips="129", seat="Circleville",
        system=RecorderSystem.CUSTOM,
        portal_url="https://pickawaycountyrecorder.com/",
        search_url_template=None,
        portal_notes="Pickaway County migrated to a new independent custom portal. Verified working.",
        phone="740-474-6005", address="207 S Court St, Circleville, OH 43113",
        records_from=1987,
    ),
    OhioCounty.PIKE: CountyInfo(
        name="Pike", fips="131", seat="Waverly",
        system=RecorderSystem.CUSTOM,
        portal_url="https://pikeohpublic.avenuinsights.com/",
        search_url_template=None,
        portal_notes="⚠️ UNVERIFIED — Pike County's official recorder page (pikecountyohcommissioners.gov/offices/recorder.html) does not link to a direct search portal. The pikeohpublic.avenuinsights.com URL loads but may not be the correct recorder search. The USLandRecords ohlr3 portal only lists Madison County — Pike has been removed. Investigator should call recorder at (740) 947-2622 or visit recorder@pikecounty.oh.gov to confirm current online access method.",
        phone="740-947-2622", address="230 Waverly Plaza Suite 500, Waverly, OH 45690",
        records_from=1987,
    ),
    OhioCounty.PORTAGE: CountyInfo(
        name="Portage", fips="133", seat="Ravenna",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=PortageOH",
        search_url_template=None,
        portal_notes="Guest access available. Grantor/grantee index available online; images may require subscription.",
        phone="330-297-3571", address="449 S Meridian St, Ravenna, OH 44266",
        records_from=1987,
    ),
    OhioCounty.PREBLE: CountyInfo(
        name="Preble", fips="135", seat="Eaton",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion9.kofiletech.us/countyweb/loginDisplay.action?countyname=PrebleOH",
        search_url_template=None,
        portal_notes="Preble County uses legacy CountyFusion (kofiletech.us). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="937-456-8160", address="101 E Main St, Eaton, OH 45320",
        records_from=1987,
    ),
    OhioCounty.PUTNAM: CountyInfo(
        name="Putnam", fips="137", seat="Ottawa",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion14.kofiletech.us/countyweb/loginDisplay.action?countyname=PutnamOH",
        search_url_template=None,
        portal_notes="Putnam County uses legacy CountyFusion (kofiletech.us). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="419-523-3659", address="245 E Main St, Ottawa, OH 45875",
        records_from=1987,
    ),
    OhioCounty.RICHLAND: CountyInfo(
        name="Richland", fips="139", seat="Mansfield",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion13.kofiletech.us/countyweb/loginDisplay.action?countyname=RichlandOH",
        search_url_template=None,
        portal_notes="Richland County uses legacy CountyFusion (countyfusion13, kofiletech.us). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="419-774-5599", address="50 Park Ave E, Mansfield, OH 44902",
        records_from=1987,
    ),
    OhioCounty.ROSS: CountyInfo(
        name="Ross", fips="141", seat="Chillicothe",
        system=RecorderSystem.CUSTOM,
        portal_url="https://www.rossrecords.us/",
        search_url_template=None,
        portal_notes=(
            "Ross County uses RossRecords.us — a custom digital platform. Independent and stable. "
            "⚠️ URL CORRECTED 2026-03-28: previous co.ross.oh.us URL returned connection error. "
            "Switched to rossrecords.us as named in documentation."
        ),
        phone="740-702-3080", address="2 N Paint St, Chillicothe, OH 45601",
        records_from=1974,
    ),
    OhioCounty.SANDUSKY: CountyInfo(
        name="Sandusky", fips="143", seat="Fremont",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion14.kofiletech.us/countyweb/loginDisplay.action?countyname=SanduskyOH",
        search_url_template=None,
        portal_notes="Sandusky County uses legacy CountyFusion (countyfusion14, kofiletech.us). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="419-334-6174", address="100 N Park Ave, Fremont, OH 43420",
        records_from=1987,
    ),
    OhioCounty.SCIOTO: CountyInfo(
        name="Scioto", fips="145", seat="Portsmouth",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohscioto.fidlar.com/OHScioto/AvaWeb/",
        search_url_template=None,
        portal_notes="Scioto County migrated to Fidlar AVA. Verified working.",
        phone="740-355-8278", address="602 7th St, Portsmouth, OH 45662",
        records_from=1987,
    ),
    OhioCounty.SENECA: CountyInfo(
        name="Seneca", fips="147", seat="Tiffin",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion13.govos.com/countyweb/loginDisplay.action?countyname=Seneca",
        search_url_template=None,
        portal_notes=(
            "Seneca County uses GovOS CountyFusion. Guest access is free — click 'Guest' "
            "on the login page. Records available from August 9, 1987. Enter names last "
            "name first (e.g., 'HOMAN DAVID'). For recent amendments and anything after "
            "the last bulk update, verify at the office directly. NOTE: Document images "
            "are NOT available online — physical visit required for certified copies."
        ),
        phone="419-447-4434",
        address="109 S Washington Street Suite 2104, Tiffin, OH 44883",
        records_from=1987,
    ),
    OhioCounty.SHELBY: CountyInfo(
        name="Shelby", fips="149", seat="Sidney",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=ShelbyOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="937-498-7226", address="129 E Court St, Sidney, OH 45365",
        records_from=1987,
    ),
    OhioCounty.STARK: CountyInfo(
        name="Stark", fips="151", seat="Canton",
        system=RecorderSystem.CUSTOM,
        portal_url="https://starkcountyohio.gov/government/offices/recorder/",
        search_url_template=None,
        portal_notes=(
            "Stark County recorder office landing page. Use this as the stable entry "
            "point for investigators to reach current records access links and office "
            "instructions. Search endpoint availability may vary. "
            "⚠️ UPDATED 2026-03-28: previous direct DTS PAXWorld URL timed out repeatedly."
        ),
        phone="330-451-7443", address="110 Central Plaza S, Canton, OH 44702",
        records_from=1987,
    ),
    OhioCounty.SUMMIT: CountyInfo(
        name="Summit", fips="153", seat="Akron",
        system=RecorderSystem.EAGLEWEB,
        portal_url="https://summitcountyoh-web.tylerhost.net/web/search/DOCSEARCH236S2",
        search_url_template=None,
        portal_notes="Summit County uses Tyler Technologies EagleWeb hosted on tylerhost.net. No login required for public index search. Confirmed working URL 2026-03-28. Prior URL (eagleweb.summitoh.net) was dead.",
        phone="330-643-2712", address="175 S Main St, Akron, OH 44308",
        records_from=1987,
    ),
    OhioCounty.TRUMBULL: CountyInfo(
        name="Trumbull", fips="155", seat="Warren",
        system=RecorderSystem.DTS_PAXWORLD,
        portal_url="https://records.co.trumbull.oh.us/PAXWorld/views/search",
        search_url_template=None,
        portal_notes=(
            "Trumbull County migrated from GovOS CountyFusion to DTS PAXWorld "
            "(Document Technology Systems) under a contract signed May 2023. "
            "No login required for public index search. URL redirects to "
            "/PAXWorld/Default on load. Confirmed accessible without VPN. "
            "NOTE: Prior recorder's DTS contract is under investigation by the "
            "Ohio Auditor (as of 2026)."
        ),
        phone="330-675-2401", address="160 High St NW, Warren, OH 44481",
        records_from=1987,
    ),
    OhioCounty.TUSCARAWAS: CountyInfo(
        name="Tuscarawas", fips="157", seat="New Philadelphia",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion10.kofiletech.us/countyweb/loginDisplay.action?countyname=TuscarawasOH",
        search_url_template=None,
        portal_notes="Tuscarawas County uses legacy CountyFusion (countyfusion10, kofiletech.us). Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="330-365-3243", address="125 E High Ave, New Philadelphia, OH 44663",
        records_from=1987,
    ),
    OhioCounty.UNION: CountyInfo(
        name="Union", fips="159", seat="Marysville",
        system=RecorderSystem.CUSTOM,
        portal_url="https://www.unioncountyohio.gov/recorder-disclaimer",
        search_url_template=None,
        portal_notes="Union County hosts its own search portal. Index records from 1875 to current. Accept disclaimer before searching.",
        phone="937-645-3006", address="233 W 6th St, Marysville, OH 43040",
        records_from=1875,
    ),
    OhioCounty.VAN_WERT: CountyInfo(
        name="Van Wert", fips="161", seat="Van Wert",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=VanWertOH",
        search_url_template=None,
        portal_notes="Guest access available. Search by grantor/grantee last name first.",
        phone="419-238-0843", address="121 E Main St, Van Wert, OH 45891",
        records_from=1987,
    ),
    OhioCounty.VINTON: CountyInfo(
        name="Vinton", fips="163", seat="McArthur",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohvinton.fidlar.com/OHVinton/AvaWeb/",
        search_url_template=None,
        portal_notes="Vinton County migrated to Fidlar AVA. Verified working.",
        phone="740-596-3001", address="100 E Main St, McArthur, OH 45651",
        records_from=1987,
    ),
    OhioCounty.WARREN: CountyInfo(
        name="Warren", fips="165", seat="Lebanon",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohwarren.fidlar.com/OHWarren/AvaWeb/",
        search_url_template=None,
        portal_notes=(
            "Warren County uses Fidlar AVA (NOT GovOS Cloud Search as previously listed). "
            "Free public index search — all deeds indexed from 1797. No login required. "
            "Official portal at recorder.warrencountyohio.gov links to ohwarren.fidlar.com. "
            "⚠️ SYSTEM CORRECTED 2026-03-28: previous warren.oh.publicsearch.us URL returned connection error."
        ),
        phone="513-695-1382", address="406 Justice Dr, Lebanon, OH 45036",
        records_from=1797,
    ),
    OhioCounty.WASHINGTON: CountyInfo(
        name="Washington", fips="167", seat="Marietta",
        system=RecorderSystem.GOVOS_CLOUD_SEARCH,
        portal_url="https://washington.oh.publicsearch.us/",
        search_url_template="https://washington.oh.publicsearch.us/results?search=OwnerSearch&query={name}",
        portal_notes="Washington County migrated to GovOS Cloud Search. Verified working.",
        phone="740-373-6623", address="205 Putnam St, Marietta, OH 45750",
        records_from=1987,
    ),
    OhioCounty.WAYNE: CountyInfo(
        name="Wayne", fips="169", seat="Wooster",
        system=RecorderSystem.GOVOS_COUNTYFUSION,
        portal_url="https://countyfusion4.govos.com/countyweb/loginDisplay.action?countyname=WayneOH",
        search_url_template=None,
        portal_notes="Wayne County uses CountyFusion. Guest access. NOTE: Platform-wide outage confirmed 2026-03-28.",
        phone="330-287-5480", address="428 W Liberty St, Wooster, OH 44691",
        records_from=1987,
    ),
    OhioCounty.WILLIAMS: CountyInfo(
        name="Williams", fips="171", seat="Bryan",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohwilliams.fidlar.com/OHWilliams/AvaWeb/",
        search_url_template=None,
        portal_notes="Williams County uses Fidlar AVA. Verified working.",
        phone="419-636-5639", address="One Courthouse Square, Bryan, OH 43506",
        records_from=1987,
    ),
    OhioCounty.WOOD: CountyInfo(
        name="Wood", fips="173", seat="Bowling Green",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ohwood.fidlar.com/OHWood/AvaWeb/",
        search_url_template=None,
        portal_notes=(
            "Wood County uses Fidlar AVA (county-specific subdomain ohwood.fidlar.com). "
            "Free public index search — record INDEX available from 1985. "
            "Document IMAGES require Laredo Select subscription (contact office for account form). "
            "URL confirmed via official county site co.wood.oh.us/recorder/ 2026-03-28."
        ),
        phone="419-354-9150", address="One Courthouse Square, Bowling Green, OH 43402",
        records_from=1985,
    ),
    OhioCounty.WYANDOT: CountyInfo(
        name="Wyandot", fips="175", seat="Upper Sandusky",
        system=RecorderSystem.FIDLAR_AVA,
        portal_url="https://ava.fidlar.com/OHWyandot/AvaWeb/",
        search_url_template=None,
        portal_notes="Wyandot County migrated to Fidlar AVA. Verified working.",
        phone="419-294-1442", address="109 S Sandusky Ave, Upper Sandusky, OH 43351",
        records_from=1987,
    ),
}


# ---------------------------------------------------------------------------
# Public API — registry
# ---------------------------------------------------------------------------

def get_county_info(county: OhioCounty) -> CountyInfo:
    """
    Return the CountyInfo record for a given Ohio county.

    Args:
        county: OhioCounty enum value.

    Returns:
        CountyInfo with portal URL, system vendor, phone, address, etc.

    Raises:
        RecorderError: If county not found in registry (should not happen for
                       valid OhioCounty enum values).
    """
    info = _REGISTRY.get(county)
    if info is None:
        raise RecorderError(
            f"County {county.value!r} not found in registry.",
            county=county,
        )
    return info


def list_counties(
    system: RecorderSystem | None = None,
) -> list[OhioCounty]:
    """
    Return all 88 OhioCounty enum values, optionally filtered by system vendor.

    Args:
        system: If provided, only return counties using this RecorderSystem.

    Returns:
        List of OhioCounty values, sorted alphabetically by county name.

    Example:
        # All counties using GovOS Cloud Search (no login required)
        easy_counties = list_counties(system=RecorderSystem.GOVOS_CLOUD_SEARCH)
    """
    counties = list(_REGISTRY.keys())
    if system is not None:
        counties = [c for c in counties if _REGISTRY[c].system == system]
    return sorted(counties, key=lambda c: _REGISTRY[c].name)


# ---------------------------------------------------------------------------
# Public API — URL builder
# ---------------------------------------------------------------------------

def get_search_url(
    county: OhioCounty,
    grantor_grantee: str | None = None,
) -> SearchUrlResult:
    """
    Generate a direct search URL for a county recorder portal.

    For GovOS Cloud Search counties (Carroll, Clark, Ottawa, Sandusky, etc.),
    this builds a direct name search URL. For GovOS CountyFusion counties,
    this returns the login/entry URL with instructions for guest access.

    The investigator takes this URL, opens it in a browser, completes the
    search (with guest login if needed), downloads the relevant documents,
    and drops them into the Catalyst intake pipeline.

    Args:
        county:           OhioCounty enum value.
        grantor_grantee:  Name to search for. For most systems, format as
                          "LAST FIRST" (last name first) for individuals, or
                          business name as-is. Optional.

    Returns:
        SearchUrlResult with the URL, system type, and investigator instructions.

    Raises:
        RecorderError: If county is not in the registry.

    Example:
        result = get_search_url(OhioCounty.SENECA, grantor_grantee="HOMAN")
        print(result.url)
        print(result.instructions)
        # Opens browser, logs in as guest, searches for HOMAN
    """
    info = get_county_info(county)

    url = info.portal_url
    instructions = info.portal_notes

    # For Cloud Search counties with a template, build a direct name search URL
    if (
        info.system == RecorderSystem.GOVOS_CLOUD_SEARCH
        and info.search_url_template
        and grantor_grantee
    ):
        url = info.search_url_template.replace(
            "{name}", grantor_grantee.strip())
        instructions = (
            f"Direct search URL generated for '{grantor_grantee}' in "
            f"{info.name} County. No login required — results load directly. "
            f"{info.portal_notes}"
        )

    # USLANDRECORDS (Avenu) varies by county — Madison requires registration.
    # Check portal_notes for the ⚠️ REQUIRES REGISTRATION flag.
    avenu_requires_login = (
        info.system == RecorderSystem.USLANDRECORDS
        and info.portal_notes
        and "REQUIRES REGISTRATION" in info.portal_notes
    )
    requires_login = info.system in (
        RecorderSystem.GOVOS_COUNTYFUSION,
        RecorderSystem.LAREDO,
    ) or avenu_requires_login

    logger.info(
        "county_recorder get_search_url: county=%s system=%s requires_login=%s",
        county.value, info.system.value, requires_login,
    )

    return SearchUrlResult(
        county=county,
        county_name=info.name,
        url=url,
        system=info.system,
        instructions=instructions,
        requires_login=requires_login,
    )


# ---------------------------------------------------------------------------
# Public API — document parser
# ---------------------------------------------------------------------------

def parse_recorder_document(
    extracted_text: str,
    county: OhioCounty | None = None,
) -> RecorderDocument:
    """
    Parse structured fields from the extracted text of a recorder document.

    This function works on text already extracted by the PDF pipeline (PyMuPDF
    or Tesseract OCR). It uses regex patterns tuned for Ohio deed and mortgage
    language — do NOT expect 100% accuracy on all documents, especially
    handwritten or heavily formatted historical records.

    Fields parsed:
        - Instrument type (deed, mortgage, release, easement, UCC, etc.)
        - Grantor(s) and grantee(s)
        - Consideration amount (including zero-consideration detection)
        - Parcel ID
        - Recording date and instrument number
        - Book/page reference
        - Preparer name and disclaimer language

    Args:
        extracted_text: Full text extracted from the document.
        county:         OhioCounty where the document was recorded. Used for
                        context; does not change parsing behavior currently.

    Returns:
        RecorderDocument with all fields populated where found. Fields not
        found in the document are None.

    Raises:
        RecorderError: If extracted_text is empty or None.

    Example:
        doc = parse_recorder_document(extracted_text, county=OhioCounty.SENECA)
        if doc.consideration == 0.0:
            print("SIGNAL: Zero-consideration transfer")
        if doc.preparer_notes and "without benefit of title search" in doc.preparer_notes.lower():
            print("SIGNAL: Title search disclaimer present")
    """
    if not extracted_text or not extracted_text.strip():
        raise RecorderError(
            "Extracted text is empty — cannot parse recorder document.")

    text = extracted_text
    text_upper = text.upper()

    result = RecorderDocument(
        county=county,
        raw_text_snippet=text[:1000],
    )

    # --- Instrument type --------------------------------------------------
    result.instrument_type = _detect_instrument_type(text_upper)

    # --- Grantor / Grantee ------------------------------------------------
    result.grantors = _extract_party("GRANTOR", text_upper, text)
    result.grantees = _extract_party("GRANTEE", text_upper, text)
    if result.grantors:
        result.grantor = result.grantors[0]
    if result.grantees:
        result.grantee = result.grantees[0]

    # --- Consideration ----------------------------------------------------
    result.consideration, result.consideration_text = _extract_consideration(
        text_upper, text)

    # --- Parcel ID --------------------------------------------------------
    result.parcel_id = _extract_parcel_id(text_upper)

    # --- Recording date ---------------------------------------------------
    result.recording_date = _extract_recording_date(text_upper)

    # --- Instrument / document number -------------------------------------
    result.instrument_number = _extract_instrument_number(text_upper)

    # --- Book and page ----------------------------------------------------
    result.book_page = _extract_book_page(text_upper)

    # --- Legal description ------------------------------------------------
    result.legal_description = _extract_legal_description(text, text_upper)

    # --- Preparer ---------------------------------------------------------
    result.preparer, result.preparer_notes = _extract_preparer(
        text, text_upper)

    logger.info(
        "county_recorder parse_recorder_document: type=%s grantor=%r grantee=%r "
        "consideration=%s parcel=%r",
        result.instrument_type, result.grantor, result.grantee,
        result.consideration, result.parcel_id,
    )
    return result


# ---------------------------------------------------------------------------
# Parsing helpers (internal)
# ---------------------------------------------------------------------------

def _detect_instrument_type(text_upper: str) -> str | None:
    """Detect the instrument type from document text."""
    patterns = [
        (r"\bWARRANTY DEED\b",          "WARRANTY DEED"),
        (r"\bQUITCLAIM DEED\b",          "QUITCLAIM DEED"),
        (r"\bTRANSFER ON DEATH\b",       "TRANSFER ON DEATH DEED"),
        (r"\bSHERIFF.S DEED\b",          "SHERIFF'S DEED"),
        (r"\bEXECUTOR.S DEED\b",         "EXECUTOR'S DEED"),
        (r"\bFIDUCIARY DEED\b",          "FIDUCIARY DEED"),
        (r"\bDEED OF TRUST\b",           "DEED OF TRUST"),
        (r"\bSATISFACTION OF MORTGAGE\b", "SATISFACTION OF MORTGAGE"),
        (r"\bRELEASE OF MORTGAGE\b",     "RELEASE OF MORTGAGE"),
        (r"\bMORTGAGE\b",                "MORTGAGE"),
        (r"\bEASEMENT\b",                "EASEMENT"),
        (r"\bUCC.{0,5}FINANCING STATEMENT\b", "UCC FINANCING STATEMENT"),
        (r"\bFINANCING STATEMENT\b",     "UCC FINANCING STATEMENT"),
        (r"\bLEASE\b",                   "LEASE"),
        (r"\bAFFIDAVIT\b",               "AFFIDAVIT"),
        (r"\bDECLARATION\b",             "DECLARATION"),
        (r"\bSURVEY\b",                  "SURVEY/PLAT"),
        (r"\b(?:WARRANTY |QUIT.?CLAIM )?DEED\b", "DEED"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text_upper):
            return label
    return None


def _extract_party(
    role: str, text_upper: str, text: str
) -> list[str]:
    """
    Extract party names for a given role (GRANTOR or GRANTEE).

    Handles common Ohio deed formats:
      "GRANTOR: John Smith"
      "John Smith, Grantor,"
      "THIS DEED, made by JOHN SMITH, Grantor, to JANE DOE, Grantee"
    """
    names: list[str] = []

    # Pattern 1: "GRANTOR:" or "GRANTEE:" label followed by name
    label_pattern = re.compile(
        rf"{role}S?[:\s]+([A-Z][A-Z0-9\s,\.'-]{{3,80}}?)(?:\n|,\s*(?:GRANTOR|GRANTEE|WHOSE|HEREIN|PARTY|$))",
        re.IGNORECASE,
    )
    for m in label_pattern.finditer(text_upper):
        name = m.group(1).strip().strip(",")
        if len(name) > 2:
            names.append(_title_case_name(name))

    # Pattern 2: name followed by role label in parens or comma
    inline_pattern = re.compile(
        rf"([A-Z][A-Z0-9\s,\.'-]{{3,80}}?),?\s*\({role}\)",
        re.IGNORECASE,
    )
    for m in inline_pattern.finditer(text_upper):
        name = m.group(1).strip().strip(",")
        if len(name) > 2 and name not in [n.upper() for n in names]:
            names.append(_title_case_name(name))

    return names[:5]  # cap at 5 to avoid runaway parsing


def _extract_consideration(
    text_upper: str, text: str
) -> tuple[float | None, str | None]:
    """
    Extract the consideration amount.

    Ohio deeds commonly state:
      "for the sum of TEN DOLLARS ($10.00)"
      "in consideration of ONE DOLLAR ($1.00) and other valuable consideration"
      "for TEN AND NO/100 DOLLARS ($10.00)"
      "for the sum of $325,000.00"
      "without consideration" / "no consideration"
    """
    # Zero-consideration patterns — highest priority
    zero_patterns = [
        r"WITHOUT\s+CONSIDERATION",
        r"NO\s+CONSIDERATION",
        r"FOR\s+(?:THE\s+SUM\s+OF\s+)?ZERO\s+DOLLARS",
        r"CONSIDERATION\s+OF\s+ZERO",
    ]
    for pattern in zero_patterns:
        if re.search(pattern, text_upper):
            return 0.0, "Zero consideration"

    # Extract dollar amount from text
    # Match "in consideration of ... $NNN,NNN.NN" or "for the sum of $NNN,NNN.NN"
    dollar_patterns = [
        r"CONSIDERATION\s+OF[^$\n]{0,80}\$\s*([\d,]+(?:\.\d{2})?)",
        r"FOR\s+THE\s+SUM\s+OF[^$\n]{0,80}\$\s*([\d,]+(?:\.\d{2})?)",
        r"PURCHASE\s+PRICE\s+OF[^$\n]{0,30}\$\s*([\d,]+(?:\.\d{2})?)",
        r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:DOLLARS|AND\s+\d+/100)",
    ]
    for pattern in dollar_patterns:
        m = re.search(pattern, text_upper)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                amount = float(raw)
                if amount > 0:
                    return amount, f"${amount:,.2f}"
            except ValueError:
                pass

    # Nominal consideration patterns (legally significant but not real price)
    nominal_patterns = [
        r"TEN\s+DOLLARS\s+AND\s+OTHER\s+VALUABLE\s+CONSIDERATION",
        r"ONE\s+DOLLAR\s+AND\s+OTHER\s+VALUABLE\s+CONSIDERATION",
        r"OTHER\s+VALUABLE\s+CONSIDERATION",
        r"LOVE\s+AND\s+AFFECTION",
    ]
    for pattern in nominal_patterns:
        m = re.search(pattern, text_upper)
        if m:
            # Return a snippet of the actual text
            start = m.start()
            snippet = text_upper[max(0, start - 20):start + 60].strip()
            return None, snippet  # amount unknown but consideration text captured

    return None, None


def _extract_parcel_id(text_upper: str) -> str | None:
    """
    Extract parcel identification number.

    Ohio parcel IDs are typically formatted as:
      "22-001234.000" (Seneca County format: 2-digit prefix, 6-digit parcel, 3-digit suffix)
      "34-001234.0000"
      Parcel No.: 12-345678-000
    """
    patterns = [
        r"PARCEL\s+(?:ID|NO\.?|NUMBER|#)[\s:]+([A-Z0-9][-A-Z0-9\.]{5,20})",
        r"PARCEL\s+(?:IDENTIFICATION\s+)?(?:NUMBER|NO\.?)[\s:]+([A-Z0-9][-A-Z0-9\.]{5,20})",
        r"PID[\s:#]+([A-Z0-9][-A-Z0-9\.]{5,20})",
        r"(?:TAX\s+)?(?:MAP\s+)?PARCEL[\s:]+([A-Z0-9][-A-Z0-9\.]{5,20})",
        # Ohio numeric format: XX-XXXXXX.XXX or XX-XXXXXX.XXXX
        r"\b(\d{2}-\d{5,6}\.\d{3,4})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_upper)
        if m:
            return m.group(1).strip()
    return None


def _extract_recording_date(text_upper: str) -> str | None:
    """Extract the recording/filing date."""
    patterns = [
        r"(?:RECORDED|FILED)\s+(?:ON\s+)?(?:THIS\s+)?(\w+\s+\d{1,2},?\s*\d{4})",
        r"(?:RECORDING|FILING)\s+DATE[\s:]+(\d{1,2}/\d{1,2}/\d{4})",
        r"DATE\s+(?:OF\s+)?RECORDING[\s:]+(\d{1,2}/\d{1,2}/\d{4})",
        r"(?:RECEIVED|RECORDED)\s+(?:FOR\s+RECORD\s+)?(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_upper)
        if m:
            return m.group(1).strip()
    return None


def _extract_instrument_number(text_upper: str) -> str | None:
    """Extract the recorder's instrument/document number."""
    patterns = [
        r"INSTRUMENT\s+(?:NO\.?|NUMBER|#)[\s:]+([A-Z0-9-]{4,20})",
        r"DOC(?:UMENT)?\s+(?:NO\.?|NUMBER|#)[\s:]+([A-Z0-9-]{4,20})",
        r"RECEPTION\s+(?:NO\.?|NUMBER)[\s:]+([A-Z0-9-]{4,20})",
        r"RECORD(?:ING)?\s+(?:NO\.?|NUMBER|#)[\s:]+([A-Z0-9-]{4,20})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_upper)
        if m:
            return m.group(1).strip()
    return None


def _extract_book_page(text_upper: str) -> str | None:
    """Extract book and page reference."""
    patterns = [
        r"BOOK\s+(\d+)\s*,?\s*PAGE\s+(\d+)",
        r"VOL(?:UME)?\s+(\d+)\s*,?\s*PAGE\s+(\d+)",
        r"OR\s+BOOK\s+(\d+)\s*,?\s*PAGE\s+(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_upper)
        if m:
            return f"Book {m.group(1)} Page {m.group(2)}"
    return None


def _extract_legal_description(text: str, text_upper: str) -> str | None:
    """
    Extract the beginning of the legal description.

    Ohio deeds typically introduce the legal description with phrases like:
    "Situated in...", "Being in...", "Located in...", "The following described..."
    """
    patterns = [
        r"(?:SITUATED|BEING|LOCATED)\s+IN\s+(?:THE\s+)?(?:TOWNSHIP|CITY|VILLAGE)",
        r"THE\s+FOLLOWING\s+DESCRIBED\s+(?:REAL\s+)?PROPERTY",
        r"LEGAL\s+DESCRIPTION\s*:",
    ]
    for pattern in patterns:
        m = re.search(pattern, text_upper)
        if m:
            start = m.start()
            snippet = text[start:start + 500].strip()
            return snippet
    return None


def _extract_preparer(
    text: str, text_upper: str
) -> tuple[str | None, str | None]:
    """
    Extract preparer name and any disclaimer language.

    Ohio attorneys sometimes include disclaimers like:
      "Prepared by: John Smith, Attorney at Law"
      "This instrument was prepared without benefit of title search"
    The title search disclaimer is investigatively significant — it's a red flag
    when the same attorney uses it repeatedly on related-party transactions.
    """
    preparer: str | None = None
    preparer_notes: str | None = None

    # Preparer name
    prep_patterns = [
        r"PREPARED\s+BY[\s:]+([A-Z][A-Za-z\s\.,'-]{5,60}?)(?:\n|,\s*(?:ATTORNEY|ESQ|NOTARY))",
        r"DRAFTED\s+BY[\s:]+([A-Z][A-Za-z\s\.,'-]{5,60}?)(?:\n|,\s*(?:ATTORNEY|ESQ))",
        r"THIS\s+INSTRUMENT\s+PREPARED\s+BY[\s:]+([A-Z][A-Za-z\s\.,'-]{5,60}?)(?:\n|\.)",
    ]
    for pattern in prep_patterns:
        m = re.search(pattern, text_upper)
        if m:
            preparer = _title_case_name(m.group(1).strip().strip(","))
            break

    # Title search disclaimer — investigatively significant
    disclaimer_patterns = [
        r"WITHOUT\s+BENEFIT\s+OF\s+TITLE\s+SEARCH",
        r"WITHOUT\s+(?:THE\s+)?BENEFIT\s+OF\s+AN?\s+ABSTRACT",
        r"WITHOUT\s+(?:A\s+)?TITLE\s+(?:EXAMINATION|SEARCH|REVIEW)",
        r"NO\s+TITLE\s+(?:EXAMINATION|SEARCH|REVIEW)\s+(?:WAS\s+)?(?:HAS\s+BEEN\s+)?(?:PERFORMED|CONDUCTED|MADE)",
    ]
    for pattern in disclaimer_patterns:
        m = re.search(pattern, text_upper)
        if m:
            start = m.start()
            # Capture a window around the disclaimer
            preparer_notes = text[max(0, start - 30):start + 100].strip()
            break

    return preparer, preparer_notes


def _title_case_name(name: str) -> str:
    """Convert an ALL-CAPS name to Title Case, preserving common name patterns."""
    # Don't convert if it's already mixed case
    if name != name.upper():
        return name.strip()
    # Simple title case — handles most names
    words = name.strip().split()
    result = []
    for word in words:
        # Preserve LLC, INC, etc.
        if word in ("LLC", "INC", "CORP", "LTD", "LP", "LLP", "PC", "II", "III", "IV", "JR", "SR"):
            result.append(word)
        else:
            result.append(word.capitalize())
    return " ".join(result)
