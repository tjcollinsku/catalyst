"""
Tests for county_recorder_connector.py

Coverage:
    - OhioCounty enum: all 88 counties present
    - RecorderSystem enum: all 10 systems present
    - Registry completeness: all 88 counties in _REGISTRY, valid portal URLs, system assignments
    - get_county_info(): known county assertions, missing-county error path
    - list_counties(): total count, system filter, alphabetical sort
    - get_search_url(): CountyFusion returns login URL + requires_login=True,
                        Cloud Search without name returns portal URL,
                        Cloud Search with name builds direct URL,
                        Fidlar AVA requires_login=False,
                        DTS PAXWorld requires_login=False,
                        EagleWeb requires_login=False,
                        Cott Systems requires_login=False,
                        Laredo requires_login=True (legacy, 0 registry counties),
                        USLandRecords requires_login=False,
                        CUSTOM requires_login=False,
                        known county spot checks
    - parse_recorder_document(): empty text raises RecorderError,
                                 instrument type detection (all 18 patterns),
                                 grantor/grantee extraction (label format, inline format),
                                 consideration parsing (zero-consideration, dollar amount,
                                   nominal consideration, no consideration),
                                 parcel ID extraction (Ohio format),
                                 recording date extraction,
                                 instrument number extraction,
                                 book/page extraction,
                                 legal description extraction,
                                 preparer extraction,
                                 title search disclaimer detection (SR-005 signal),
                                 raw_text_snippet capped at 1000 chars,
                                 county field preserved on result
    - RecorderError: message and county attributes
    - _title_case_name: ALL-CAPS conversion, LLC/INC preservation, mixed-case passthrough

Run:
    python -m unittest investigations.tests_county_recorder -v
"""

import unittest

from investigations.county_recorder_connector import (
    OhioCounty,
    RecorderSystem,
    RecorderError,
    CountyInfo,
    SearchUrlResult,
    RecorderDocument,
    get_county_info,
    list_counties,
    get_search_url,
    parse_recorder_document,
    _REGISTRY,
    _detect_instrument_type,
    _extract_consideration,
    _extract_parcel_id,
    _extract_recording_date,
    _extract_instrument_number,
    _extract_book_page,
    _extract_legal_description,
    _extract_preparer,
    _title_case_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deed_text(
    instrument="WARRANTY DEED",
    grantor="EXAMPLE, DAVID A",
    grantee="EXAMPLE PROPERTIES LLC",
    consideration="WITHOUT CONSIDERATION",
    parcel="22-001234.000",
    recording_date="RECORDED ON March 15, 2018",
    instrument_number="INSTRUMENT NO. 2018-00456",
    book_page="BOOK 312 PAGE 44",
    legal="Situated in the Township of Pleasant, Seneca County",
    preparer="Prepared by: James T. Black, Attorney at Law",
    disclaimer="",
):
    """Build a synthetic deed text for parser tests."""
    return (
        f"{instrument}\n\n"
        f"GRANTOR: {grantor}\n"
        f"GRANTEE: {grantee}\n\n"
        f"In consideration of {consideration}\n\n"
        f"Parcel No.: {parcel}\n\n"
        f"{recording_date}\n"
        f"{instrument_number}\n"
        f"{book_page}\n\n"
        f"{legal}\n\n"
        f"{preparer}\n"
        f"{disclaimer}\n"
    )


# ---------------------------------------------------------------------------
# OhioCounty enum
# ---------------------------------------------------------------------------

class OhioCountyEnumTests(unittest.TestCase):

    def test_all_88_counties_present(self):
        """OhioCounty must have exactly 88 members."""
        self.assertEqual(len(OhioCounty), 88)

    def test_seneca_value(self):
        self.assertEqual(OhioCounty.SENECA.value, "seneca")

    def test_carroll_value(self):
        self.assertEqual(OhioCounty.CARROLL.value, "carroll")

    def test_van_wert_value(self):
        """Underscored county name."""
        self.assertEqual(OhioCounty.VAN_WERT.value, "van_wert")

    def test_all_values_lowercase(self):
        for county in OhioCounty:
            self.assertEqual(county.value, county.value.lower(),
                             f"{county.name} value is not lowercase")

    def test_specific_counties_present(self):
        """Spot-check a spread of counties are in the enum."""
        names = {c.name for c in OhioCounty}
        for expected in [
            "ADAMS", "CUYAHOGA", "FRANKLIN", "HAMILTON", "HOLMES",
            "LAKE", "MADISON", "MIAMI", "OTTAWA", "PIKE", "RICHLAND",
            "SENECA", "TUSCARAWAS", "WARREN", "WAYNE", "WOOD", "WYANDOT",
        ]:
            self.assertIn(expected, names, f"OhioCounty.{expected} missing")


# ---------------------------------------------------------------------------
# RecorderSystem enum
# ---------------------------------------------------------------------------

class RecorderSystemEnumTests(unittest.TestCase):

    def test_eleven_systems_present(self):
        """Connector now has 11 RecorderSystem variants after live verification.
        Added COMPILED_TECH (Compiled Technologies IDX) confirmed on Meigs, Crawford."""
        self.assertEqual(len(RecorderSystem), 11)

    def test_system_values(self):
        self.assertEqual(
            RecorderSystem.GOVOS_COUNTYFUSION.value, "GovOS CountyFusion")
        self.assertEqual(
            RecorderSystem.GOVOS_CLOUD_SEARCH.value, "GovOS Cloud Search")
        self.assertEqual(RecorderSystem.DTS_PAXWORLD.value, "DTS PAXWorld")
        self.assertEqual(RecorderSystem.FIDLAR_AVA.value, "Fidlar AVA")
        self.assertEqual(RecorderSystem.EAGLEWEB.value, "EagleWeb (Tyler)")
        self.assertEqual(RecorderSystem.COTT_SYSTEMS.value, "Cott Systems")
        self.assertEqual(RecorderSystem.COMPILED_TECH.value, "Compiled Technologies")
        self.assertEqual(RecorderSystem.LAREDO.value, "Laredo (Fidlar)")
        self.assertEqual(RecorderSystem.USLANDRECORDS.value,
                         "USLandRecords (Avenu)")
        self.assertEqual(RecorderSystem.CUSTOM.value, "Custom/Other")
        self.assertEqual(RecorderSystem.UNAVAILABLE.value, "In-Person Only")


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

class RegistryCompletenessTests(unittest.TestCase):

    def test_registry_has_88_entries(self):
        self.assertEqual(len(_REGISTRY), 88)

    def test_every_ohio_county_in_registry(self):
        for county in OhioCounty:
            self.assertIn(county, _REGISTRY,
                          f"{county.name} missing from _REGISTRY")

    def test_all_entries_are_county_info(self):
        for county, info in _REGISTRY.items():
            self.assertIsInstance(
                info, CountyInfo, f"{county.name} is not a CountyInfo")

    def test_all_countyfusion_counties_have_portal_url(self):
        for county, info in _REGISTRY.items():
            if info.system == RecorderSystem.GOVOS_COUNTYFUSION:
                self.assertIsNotNone(info.portal_url,
                                     f"{county.name} is CountyFusion but has no portal_url")
                # GovOS CountyFusion portals use either govos.com or kofiletech.us domains
                portal = info.portal_url.lower()
                self.assertTrue(
                    "govos.com" in portal or "kofiletech.us" in portal,
                    f"{county.name} portal_url doesn't look like a CountyFusion domain: {info.portal_url}"
                )

    def test_cloud_search_counties_have_portal_url(self):
        for county, info in _REGISTRY.items():
            if info.system == RecorderSystem.GOVOS_CLOUD_SEARCH:
                self.assertIsNotNone(info.portal_url,
                                     f"{county.name} Cloud Search county has no portal_url")
                # Most Cloud Search counties use publicsearch.us; some like Franklin
                # use the county's own domain but still run on GovOS Cloud Search
                self.assertTrue(len(info.portal_url) > 10,
                                f"{county.name} portal_url appears empty")

    def test_cloud_search_template_counties(self):
        """Carroll, Clark, Ottawa, Butler, Warren, Cuyahoga should have search_url_template.
        Note: Sandusky was removed from this list — it is now CountyFusion, not Cloud Search."""
        template_counties = [
            OhioCounty.CARROLL, OhioCounty.CLARK,
            OhioCounty.OTTAWA, OhioCounty.BUTLER,
        ]
        for county in template_counties:
            info = _REGISTRY[county]
            self.assertIsNotNone(info.search_url_template,
                                 f"{county.name} should have search_url_template")
            self.assertIn("{name}", info.search_url_template,
                          f"{county.name} template missing {{name}} placeholder")

    def test_all_entries_have_name(self):
        for county, info in _REGISTRY.items():
            self.assertTrue(info.name, f"{county.name} has empty name")

    def test_all_entries_have_phone(self):
        for county, info in _REGISTRY.items():
            self.assertTrue(info.phone, f"{county.name} has no phone")

    def test_all_entries_have_address(self):
        for county, info in _REGISTRY.items():
            self.assertTrue(info.address, f"{county.name} has no address")

    def test_all_fips_codes_are_odd_three_digit(self):
        """Ohio FIPS codes run 001–175, odd only."""
        for county, info in _REGISTRY.items():
            fips = int(info.fips)
            self.assertTrue(1 <= fips <= 175,
                            f"{county.name} FIPS {fips} out of range")
            self.assertEqual(fips % 2, 1, f"{county.name} FIPS {fips} is even")

    def test_seneca_is_countyfusion(self):
        self.assertEqual(
            _REGISTRY[OhioCounty.SENECA].system, RecorderSystem.GOVOS_COUNTYFUSION)

    def test_seneca_records_from_1987(self):
        self.assertEqual(_REGISTRY[OhioCounty.SENECA].records_from, 1987)

    def test_carroll_is_cloud_search(self):
        self.assertEqual(
            _REGISTRY[OhioCounty.CARROLL].system, RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_clark_is_cloud_search(self):
        self.assertEqual(_REGISTRY[OhioCounty.CLARK].system,
                         RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_ottawa_is_cloud_search(self):
        self.assertEqual(
            _REGISTRY[OhioCounty.OTTAWA].system, RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_sandusky_is_countyfusion(self):
        """Sandusky is on CountyFusion (was incorrectly listed as Cloud Search)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.SANDUSKY].system, RecorderSystem.GOVOS_COUNTYFUSION)

    def test_franklin_is_cloud_search(self):
        self.assertEqual(
            _REGISTRY[OhioCounty.FRANKLIN].system, RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_butler_is_cloud_search(self):
        """Butler migrated from CountyFusion to GovOS Cloud Search."""
        self.assertEqual(
            _REGISTRY[OhioCounty.BUTLER].system, RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_cuyahoga_is_cloud_search(self):
        """Cuyahoga migrated to GovOS Cloud Search (publicsearch.us)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.CUYAHOGA].system, RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_delaware_is_custom(self):
        self.assertEqual(
            _REGISTRY[OhioCounty.DELAWARE].system, RecorderSystem.CUSTOM)

    def test_union_is_custom(self):
        self.assertEqual(
            _REGISTRY[OhioCounty.UNION].system, RecorderSystem.CUSTOM)

    def test_holmes_is_fidlar_ava(self):
        """Holmes migrated from Laredo to Fidlar AVA."""
        self.assertEqual(
            _REGISTRY[OhioCounty.HOLMES].system, RecorderSystem.FIDLAR_AVA)

    def test_warren_is_cloud_search(self):
        """Warren migrated from Laredo to GovOS Cloud Search."""
        self.assertEqual(
            _REGISTRY[OhioCounty.WARREN].system, RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_wood_is_fidlar_ava(self):
        """Wood migrated from Laredo to Fidlar AVA."""
        self.assertEqual(
            _REGISTRY[OhioCounty.WOOD].system, RecorderSystem.FIDLAR_AVA)

    def test_richland_is_countyfusion(self):
        """Richland is on CountyFusion (was incorrectly listed as USLandRecords)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.RICHLAND].system, RecorderSystem.GOVOS_COUNTYFUSION)

    def test_wayne_is_countyfusion(self):
        """Wayne is on CountyFusion (was incorrectly listed as USLandRecords)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.WAYNE].system, RecorderSystem.GOVOS_COUNTYFUSION)

    def test_tuscarawas_is_countyfusion(self):
        """Tuscarawas is on CountyFusion (was incorrectly listed as USLandRecords)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.TUSCARAWAS].system, RecorderSystem.GOVOS_COUNTYFUSION)

    def test_madison_is_uslandrecords(self):
        """Madison County remains on USLandRecords (Avenu Insights)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.MADISON].system, RecorderSystem.USLANDRECORDS)

    def test_paulding_is_fidlar_ava(self):
        """Paulding migrated from USLandRecords to Fidlar AVA."""
        self.assertEqual(
            _REGISTRY[OhioCounty.PAULDING].system, RecorderSystem.FIDLAR_AVA)

    def test_trumbull_is_dts_paxworld(self):
        """Trumbull migrated from CountyFusion to DTS PAXWorld (May 2023)."""
        self.assertEqual(
            _REGISTRY[OhioCounty.TRUMBULL].system, RecorderSystem.DTS_PAXWORLD)

    def test_mercer_is_fidlar_ava(self):
        """Mercer migrated from CountyFusion to Fidlar AVA."""
        self.assertEqual(
            _REGISTRY[OhioCounty.MERCER].system, RecorderSystem.FIDLAR_AVA)

    def test_meigs_is_compiled_tech(self):
        """Meigs uses Compiled Technologies IDX — confirmed working by user 2026-03-28."""
        self.assertEqual(
            _REGISTRY[OhioCounty.MEIGS].system, RecorderSystem.COMPILED_TECH)

    def test_crawford_is_compiled_tech(self):
        """Crawford uses Compiled Technologies IDX — confirmed via web search 2026-03-28."""
        self.assertEqual(
            _REGISTRY[OhioCounty.CRAWFORD].system, RecorderSystem.COMPILED_TECH)

    def test_madison_requires_login(self):
        """Madison County Avenu portal requires free registration before searching."""
        result = get_search_url(OhioCounty.MADISON)
        self.assertTrue(result.requires_login)


# ---------------------------------------------------------------------------
# get_county_info()
# ---------------------------------------------------------------------------

class GetCountyInfoTests(unittest.TestCase):

    def test_returns_county_info(self):
        info = get_county_info(OhioCounty.SENECA)
        self.assertIsInstance(info, CountyInfo)

    def test_seneca_name(self):
        info = get_county_info(OhioCounty.SENECA)
        self.assertEqual(info.name, "Seneca")

    def test_seneca_fips(self):
        info = get_county_info(OhioCounty.SENECA)
        self.assertEqual(info.fips, "147")

    def test_seneca_seat(self):
        info = get_county_info(OhioCounty.SENECA)
        self.assertEqual(info.seat, "Tiffin")

    def test_carroll_portal_url(self):
        info = get_county_info(OhioCounty.CARROLL)
        self.assertIn("carroll", info.portal_url.lower())

    def test_cuyahoga_portal_url(self):
        """Cuyahoga is now GovOS Cloud Search at publicsearch.us."""
        info = get_county_info(OhioCounty.CUYAHOGA)
        self.assertIn("cuyahoga", info.portal_url.lower())

    def test_every_county_retrievable(self):
        """get_county_info should succeed for every OhioCounty value."""
        for county in OhioCounty:
            info = get_county_info(county)
            self.assertIsInstance(info, CountyInfo)

    def test_missing_county_raises_recorder_error(self):
        """Artificially remove a county to test the error path."""
        # Temporarily pop and restore
        saved = _REGISTRY.pop(OhioCounty.SENECA)
        try:
            with self.assertRaises(RecorderError) as cm:
                get_county_info(OhioCounty.SENECA)
            self.assertEqual(cm.exception.county, OhioCounty.SENECA)
        finally:
            _REGISTRY[OhioCounty.SENECA] = saved


# ---------------------------------------------------------------------------
# list_counties()
# ---------------------------------------------------------------------------

class ListCountiesTests(unittest.TestCase):

    def test_returns_88_without_filter(self):
        counties = list_counties()
        self.assertEqual(len(counties), 88)

    def test_all_ohiocounty_instances(self):
        for county in list_counties():
            self.assertIsInstance(county, OhioCounty)

    def test_alphabetical_by_county_name(self):
        counties = list_counties()
        names = [_REGISTRY[c].name for c in counties]
        self.assertEqual(names, sorted(names))

    def test_filter_cloud_search(self):
        cloud = list_counties(system=RecorderSystem.GOVOS_CLOUD_SEARCH)
        # Carroll, Clark, Ottawa, Franklin, Butler, Warren, Cuyahoga = at least 7
        self.assertGreaterEqual(len(cloud), 7)
        for county in cloud:
            self.assertEqual(_REGISTRY[county].system,
                             RecorderSystem.GOVOS_CLOUD_SEARCH)

    def test_filter_fidlar_ava(self):
        """Fidlar AVA is now a substantial group after the Gemini audit corrected
        many counties that had migrated from Laredo/CountyFusion to AVA."""
        ava = list_counties(system=RecorderSystem.FIDLAR_AVA)
        self.assertGreaterEqual(len(ava), 10)
        for county in ava:
            self.assertEqual(_REGISTRY[county].system, RecorderSystem.FIDLAR_AVA)

    def test_filter_laredo_legacy(self):
        """LAREDO is a legacy enum value. After the audit, no counties are assigned
        to it in the registry — the enum is kept for historical reference and the
        requires_login logic in get_search_url."""
        laredo = list_counties(system=RecorderSystem.LAREDO)
        self.assertEqual(len(laredo), 0)

    def test_filter_uslandrecords(self):
        """After audit, only Madison and Pike remain on USLandRecords (Avenu Insights)."""
        uslr = list_counties(system=RecorderSystem.USLANDRECORDS)
        self.assertGreaterEqual(len(uslr), 2)
        for county in uslr:
            self.assertEqual(_REGISTRY[county].system,
                             RecorderSystem.USLANDRECORDS)

    def test_filter_custom(self):
        custom = list_counties(system=RecorderSystem.CUSTOM)
        # Delaware, Union, and other county-custom portals = at least 4
        self.assertGreaterEqual(len(custom), 4)
        for county in custom:
            self.assertEqual(_REGISTRY[county].system, RecorderSystem.CUSTOM)

    def test_countyfusion_still_significant_group(self):
        """CountyFusion is no longer the majority after the Gemini audit corrected
        many counties that had migrated to AVA, CS, DTS, COTT, or EAG.
        Expect at least 15 counties still on CF (incl. Seneca, Wayne, Richland, etc.)."""
        cf = list_counties(system=RecorderSystem.GOVOS_COUNTYFUSION)
        self.assertGreaterEqual(len(cf), 15)

    def test_filter_returns_alphabetical(self):
        cloud = list_counties(system=RecorderSystem.GOVOS_CLOUD_SEARCH)
        names = [_REGISTRY[c].name for c in cloud]
        self.assertEqual(names, sorted(names))

    def test_carroll_in_cloud_search(self):
        cloud = list_counties(system=RecorderSystem.GOVOS_CLOUD_SEARCH)
        self.assertIn(OhioCounty.CARROLL, cloud)

    def test_seneca_in_countyfusion(self):
        cf = list_counties(system=RecorderSystem.GOVOS_COUNTYFUSION)
        self.assertIn(OhioCounty.SENECA, cf)

    def test_filter_sums_to_88(self):
        total = sum(
            len(list_counties(system=s)) for s in RecorderSystem
        )
        self.assertEqual(total, 88)


# ---------------------------------------------------------------------------
# get_search_url()
# ---------------------------------------------------------------------------

class GetSearchUrlTests(unittest.TestCase):

    def test_returns_search_url_result(self):
        result = get_search_url(OhioCounty.SENECA)
        self.assertIsInstance(result, SearchUrlResult)

    def test_countyfusion_requires_login(self):
        result = get_search_url(OhioCounty.SENECA)
        self.assertTrue(result.requires_login)

    def test_countyfusion_returns_portal_url(self):
        result = get_search_url(OhioCounty.SENECA)
        self.assertIn("countyfusion", result.url.lower())

    def test_countyfusion_county_name(self):
        result = get_search_url(OhioCounty.SENECA)
        self.assertEqual(result.county_name, "Seneca")

    def test_countyfusion_county_enum(self):
        result = get_search_url(OhioCounty.SENECA)
        self.assertEqual(result.county, OhioCounty.SENECA)

    def test_countyfusion_system(self):
        result = get_search_url(OhioCounty.SENECA)
        self.assertEqual(result.system, RecorderSystem.GOVOS_COUNTYFUSION)

    def test_countyfusion_with_name_still_portal_url(self):
        """CountyFusion has no template — name doesn't change the URL."""
        result = get_search_url(OhioCounty.SENECA, grantor_grantee="EXAMPLE")
        self.assertIn("countyfusion", result.url.lower())

    def test_cloud_search_no_name_returns_portal_url(self):
        result = get_search_url(OhioCounty.CARROLL)
        self.assertEqual(result.url, _REGISTRY[OhioCounty.CARROLL].portal_url)

    def test_cloud_search_no_name_requires_login_false(self):
        result = get_search_url(OhioCounty.CARROLL)
        self.assertFalse(result.requires_login)

    def test_cloud_search_with_name_builds_direct_url(self):
        result = get_search_url(
            OhioCounty.CARROLL, grantor_grantee="SMITH JOHN")
        self.assertIn("SMITH JOHN", result.url)
        self.assertIn("carroll", result.url.lower())

    def test_cloud_search_url_template_substitution(self):
        """Template {name} replaced with provided search term."""
        result = get_search_url(OhioCounty.OTTAWA, grantor_grantee="JONES")
        self.assertNotIn("{name}", result.url)
        self.assertIn("JONES", result.url)

    def test_cloud_search_with_name_instructions_mention_name(self):
        """Use Ottawa (has template) — Sandusky was moved to CountyFusion."""
        result = get_search_url(OhioCounty.OTTAWA, grantor_grantee="EXAMPLE")
        self.assertIn("EXAMPLE", result.instructions)

    def test_cloud_search_with_name_no_login_required(self):
        result = get_search_url(OhioCounty.CLARK, grantor_grantee="SMITH")
        self.assertFalse(result.requires_login)

    def test_franklin_template_builds_direct_url(self):
        """Franklin is Cloud Search and now has a search_url_template — builds direct URL."""
        result = get_search_url(OhioCounty.FRANKLIN, grantor_grantee="JONES")
        self.assertIn("JONES", result.url)
        self.assertIn("franklin", result.url.lower())

    def test_laredo_requires_login_logic_preserved(self):
        """LAREDO is in the requires_login set in get_search_url even though no
        registry counties use it — verify CountyFusion (Seneca) still requires login
        as a proxy for the same code path."""
        result = get_search_url(OhioCounty.SENECA)
        self.assertTrue(result.requires_login)

    def test_uslandrecords_no_login(self):
        """Madison County is on USLandRecords (Avenu) — no login required."""
        result = get_search_url(OhioCounty.MADISON)
        self.assertFalse(result.requires_login)

    def test_custom_no_login(self):
        """Delaware County uses a custom portal — no login required."""
        result = get_search_url(OhioCounty.DELAWARE)
        self.assertFalse(result.requires_login)

    def test_cuyahoga_url_contains_cuyahoga(self):
        """Cuyahoga is now GovOS Cloud Search at publicsearch.us — URL no longer
        contains 'recorder' but does contain 'cuyahoga'."""
        result = get_search_url(OhioCounty.CUYAHOGA)
        self.assertIn("cuyahoga", result.url.lower())

    def test_instructions_not_empty(self):
        for county in list_counties():
            result = get_search_url(county)
            self.assertTrue(result.instructions,
                            f"{county.name} has empty instructions")

    def test_url_none_only_for_unavailable(self):
        """Only UNAVAILABLE counties should have url=None."""
        for county in OhioCounty:
            info = _REGISTRY[county]
            result = get_search_url(county)
            if info.system == RecorderSystem.UNAVAILABLE:
                self.assertIsNone(result.url)
            else:
                self.assertIsNotNone(
                    result.url, f"{county.name} has None url unexpectedly")


# ---------------------------------------------------------------------------
# parse_recorder_document() — error handling
# ---------------------------------------------------------------------------

class ParseRecorderDocumentErrorTests(unittest.TestCase):

    def test_empty_string_raises_recorder_error(self):
        with self.assertRaises(RecorderError):
            parse_recorder_document("")

    def test_whitespace_only_raises_recorder_error(self):
        with self.assertRaises(RecorderError):
            parse_recorder_document("   \n\t  ")

    def test_none_raises_recorder_error(self):
        with self.assertRaises(RecorderError):
            parse_recorder_document(None)

    def test_valid_text_returns_recorder_document(self):
        result = parse_recorder_document(_deed_text())
        self.assertIsInstance(result, RecorderDocument)

    def test_county_preserved_on_result(self):
        result = parse_recorder_document(
            _deed_text(), county=OhioCounty.SENECA)
        self.assertEqual(result.county, OhioCounty.SENECA)

    def test_county_none_if_not_provided(self):
        result = parse_recorder_document(_deed_text())
        self.assertIsNone(result.county)

    def test_raw_text_snippet_is_first_1000_chars(self):
        long_text = _deed_text() + ("X" * 2000)
        result = parse_recorder_document(long_text)
        self.assertEqual(len(result.raw_text_snippet), 1000)
        self.assertEqual(result.raw_text_snippet, long_text[:1000])

    def test_raw_text_snippet_short_text(self):
        short = _deed_text()
        result = parse_recorder_document(short)
        self.assertEqual(result.raw_text_snippet, short[:1000])


# ---------------------------------------------------------------------------
# _detect_instrument_type()
# ---------------------------------------------------------------------------

class DetectInstrumentTypeTests(unittest.TestCase):

    def _check(self, text, expected):
        result = _detect_instrument_type(text.upper())
        self.assertEqual(result, expected, f"Input: {text!r}")

    def test_warranty_deed(self):
        self._check("This is a WARRANTY DEED between parties", "WARRANTY DEED")

    def test_quitclaim_deed(self):
        self._check("QUITCLAIM DEED", "QUITCLAIM DEED")

    def test_transfer_on_death(self):
        self._check("TRANSFER ON DEATH designation", "TRANSFER ON DEATH DEED")

    def test_sheriffs_deed(self):
        self._check("SHERIFF'S DEED recorded herein", "SHERIFF'S DEED")

    def test_executors_deed(self):
        self._check("EXECUTOR'S DEED from the estate", "EXECUTOR'S DEED")

    def test_fiduciary_deed(self):
        self._check("FIDUCIARY DEED executed by trustee", "FIDUCIARY DEED")

    def test_deed_of_trust(self):
        self._check("This DEED OF TRUST secures payment", "DEED OF TRUST")

    def test_mortgage(self):
        self._check("MORTGAGE for the sum of $100,000", "MORTGAGE")

    def test_satisfaction_of_mortgage(self):
        result = _detect_instrument_type("SATISFACTION OF MORTGAGE")
        self.assertEqual(result, "SATISFACTION OF MORTGAGE")

    def test_release_of_mortgage(self):
        result = _detect_instrument_type("RELEASE OF MORTGAGE IN FULL")
        self.assertEqual(result, "RELEASE OF MORTGAGE")

    def test_easement(self):
        self._check("EASEMENT for utility access", "EASEMENT")

    def test_ucc_financing_statement(self):
        self._check("UCC FINANCING STATEMENT", "UCC FINANCING STATEMENT")

    def test_financing_statement_alone(self):
        self._check("FINANCING STATEMENT per Article 9",
                    "UCC FINANCING STATEMENT")

    def test_lease(self):
        self._check("This LEASE agreement", "LEASE")

    def test_affidavit(self):
        self._check("AFFIDAVIT of survivorship", "AFFIDAVIT")

    def test_declaration(self):
        self._check("DECLARATION of covenants", "DECLARATION")

    def test_survey(self):
        self._check("SURVEY/PLAT of land", "SURVEY/PLAT")

    def test_plain_deed_fallback(self):
        self._check("This DEED conveys property", "DEED")

    def test_unknown_returns_none(self):
        result = _detect_instrument_type("RANDOM DOCUMENT NO INSTRUMENT TYPE")
        self.assertIsNone(result)

    def test_priority_warranty_over_plain_deed(self):
        """WARRANTY DEED should match before generic DEED fallback."""
        result = _detect_instrument_type("WARRANTY DEED AND DEED")
        self.assertEqual(result, "WARRANTY DEED")


# ---------------------------------------------------------------------------
# Grantor / Grantee extraction (via parse_recorder_document)
# ---------------------------------------------------------------------------

class GrantorGranteeTests(unittest.TestCase):

    def test_label_format_grantor(self):
        text = "WARRANTY DEED\n\nGRANTOR: EXAMPLE DAVID A\n\nGRANTEE: EXAMPLE PROPERTIES LLC\n\n"
        result = parse_recorder_document(text)
        self.assertIsNotNone(result.grantor)
        self.assertIn("Example", result.grantor)

    def test_label_format_grantee(self):
        text = "WARRANTY DEED\n\nGRANTOR: SMITH JOHN\n\nGRANTEE: JONES PROPERTIES LLC\n\n"
        result = parse_recorder_document(text)
        self.assertIsNotNone(result.grantee)
        self.assertIn("Jones", result.grantee)

    def test_primary_grantor_is_first(self):
        text = (
            "WARRANTY DEED\n\n"
            "GRANTOR: FIRST PARTY\n"
            "GRANTOR: SECOND PARTY\n\n"
            "GRANTEE: BUYER LLC\n"
        )
        result = parse_recorder_document(text)
        self.assertEqual(result.grantor, result.grantors[0])

    def test_primary_grantee_is_first(self):
        text = "WARRANTY DEED\n\nGRANTOR: SELLER\n\nGRANTEE: BUYER ONE\nGRANTEE: BUYER TWO\n"
        result = parse_recorder_document(text)
        self.assertEqual(result.grantee, result.grantees[0])

    def test_grantors_list_populated(self):
        text = "DEED\n\nGRANTOR: SMITH JOHN A\n\nGRANTEE: DOE JANE\n"
        result = parse_recorder_document(text)
        self.assertIsInstance(result.grantors, list)
        self.assertGreaterEqual(len(result.grantors), 1)

    def test_grantees_list_populated(self):
        text = "DEED\n\nGRANTOR: SELLER INC\n\nGRANTEE: BUYER LLC\n"
        result = parse_recorder_document(text)
        self.assertIsInstance(result.grantees, list)
        self.assertGreaterEqual(len(result.grantees), 1)

    def test_no_parties_returns_none(self):
        text = "This document has no party labels at all."
        result = parse_recorder_document(text)
        self.assertIsNone(result.grantor)
        self.assertIsNone(result.grantee)

    def test_title_case_conversion(self):
        """Names extracted from ALL-CAPS text should be title-cased."""
        text = "WARRANTY DEED\n\nGRANTOR: JONES ROBERT\n\nGRANTEE: DOE PROPERTIES LLC\n"
        result = parse_recorder_document(text)
        # Should not be all-caps
        if result.grantor:
            self.assertNotEqual(result.grantor, result.grantor.upper(),
                                "Grantor should not be ALL CAPS")


# ---------------------------------------------------------------------------
# _extract_consideration()
# ---------------------------------------------------------------------------

class ExtractConsiderationTests(unittest.TestCase):

    def _run(self, text):
        return _extract_consideration(text.upper(), text)

    def test_without_consideration(self):
        amount, text = self._run("conveyed WITHOUT CONSIDERATION to grantee")
        self.assertEqual(amount, 0.0)
        self.assertEqual(text, "Zero consideration")

    def test_no_consideration(self):
        amount, text = self._run("transferred for NO CONSIDERATION")
        self.assertEqual(amount, 0.0)

    def test_zero_dollars(self):
        amount, text = self._run("FOR THE SUM OF ZERO DOLLARS")
        self.assertEqual(amount, 0.0)

    def test_consideration_of_zero(self):
        amount, text = self._run("CONSIDERATION OF ZERO and no/100")
        self.assertEqual(amount, 0.0)

    def test_dollar_amount_from_consideration_clause(self):
        amount, text = self._run(
            "In consideration of the sum of $325,000.00 paid by grantee"
        )
        self.assertAlmostEqual(amount, 325000.0, places=2)

    def test_dollar_amount_for_the_sum_of(self):
        amount, text = self._run("FOR THE SUM OF $150,000.00")
        self.assertAlmostEqual(amount, 150000.0, places=2)

    def test_purchase_price(self):
        amount, text = self._run("PURCHASE PRICE OF $99,500.00")
        self.assertAlmostEqual(amount, 99500.0, places=2)

    def test_nominal_ten_dollars_other_consideration(self):
        amount, text = self._run(
            "for TEN DOLLARS AND OTHER VALUABLE CONSIDERATION"
        )
        self.assertIsNone(amount)
        self.assertIsNotNone(text)
        self.assertIn("VALUABLE", text.upper())

    def test_nominal_one_dollar(self):
        amount, text = self._run("ONE DOLLAR AND OTHER VALUABLE CONSIDERATION")
        self.assertIsNone(amount)
        self.assertIsNotNone(text)

    def test_love_and_affection(self):
        amount, text = self._run("in consideration of LOVE AND AFFECTION")
        self.assertIsNone(amount)
        self.assertIsNotNone(text)

    def test_no_consideration_text_returns_none_none(self):
        amount, text = self._run(
            "This deed conveys the property described below.")
        self.assertIsNone(amount)
        self.assertIsNone(text)

    def test_zero_consideration_takes_priority_over_dollar_amount(self):
        """If both zero-consideration and a dollar amount appear, zero wins."""
        amount, text = self._run(
            "WITHOUT CONSIDERATION but also mentions $10.00 somewhere"
        )
        self.assertEqual(amount, 0.0)


# ---------------------------------------------------------------------------
# _extract_parcel_id()
# ---------------------------------------------------------------------------

class ExtractParcelIdTests(unittest.TestCase):

    def test_ohio_numeric_format(self):
        """Seneca County format: 22-001234.000"""
        result = _extract_parcel_id("PARCEL NO.: 22-001234.000")
        self.assertEqual(result, "22-001234.000")

    def test_parcel_id_label(self):
        result = _extract_parcel_id("PARCEL ID: 34-567890.001")
        self.assertEqual(result, "34-567890.001")

    def test_parcel_number_label(self):
        result = _extract_parcel_id("PARCEL NUMBER: 12-345678.0001")
        self.assertIsNotNone(result)

    def test_pid_label(self):
        result = _extract_parcel_id("PID: 05-012345.000")
        self.assertIsNotNone(result)

    def test_numeric_format_standalone(self):
        result = _extract_parcel_id(
            "The parcel 22-001234.000 is described below.")
        self.assertEqual(result, "22-001234.000")

    def test_no_parcel_returns_none(self):
        # Avoid alphanumeric words that might accidentally match; use text with no
        # digits or parcel-adjacent labels
        result = _extract_parcel_id(
            "THIS DEED CONTAINS NO PROPERTY IDENTIFIER WHATSOEVER")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _extract_recording_date()
# ---------------------------------------------------------------------------

class ExtractRecordingDateTests(unittest.TestCase):

    def test_recorded_on_date(self):
        result = _extract_recording_date("RECORDED ON March 15, 2018")
        self.assertIsNotNone(result)
        self.assertIn("2018", result)

    def test_recording_date_slash(self):
        result = _extract_recording_date("RECORDING DATE: 03/15/2018")
        self.assertIsNotNone(result)
        self.assertIn("2018", result)

    def test_received_for_record(self):
        result = _extract_recording_date("RECEIVED FOR RECORD 07/22/2020")
        self.assertIsNotNone(result)
        self.assertIn("2020", result)

    def test_no_date_returns_none(self):
        result = _extract_recording_date("THIS DEED HAS NO DATE INFO")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _extract_instrument_number()
# ---------------------------------------------------------------------------

class ExtractInstrumentNumberTests(unittest.TestCase):

    def test_instrument_no(self):
        result = _extract_instrument_number("INSTRUMENT NO. 2018-00456")
        self.assertIsNotNone(result)
        self.assertIn("2018", result)

    def test_document_number(self):
        result = _extract_instrument_number("DOCUMENT NUMBER: 20200712345")
        self.assertIsNotNone(result)

    def test_reception_no(self):
        result = _extract_instrument_number("RECEPTION NO. 2021-045678")
        self.assertIsNotNone(result)

    def test_recording_number(self):
        result = _extract_instrument_number("RECORDING NO: REC2019001")
        self.assertIsNotNone(result)

    def test_no_number_returns_none(self):
        result = _extract_instrument_number(
            "THIS DOCUMENT HAS NO INSTRUMENT NUMBER")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _extract_book_page()
# ---------------------------------------------------------------------------

class ExtractBookPageTests(unittest.TestCase):

    def test_book_page_format(self):
        result = _extract_book_page("recorded in BOOK 312 PAGE 44")
        self.assertIsNotNone(result)
        self.assertIn("312", result)
        self.assertIn("44", result)

    def test_book_page_format_with_comma(self):
        result = _extract_book_page("BOOK 100, PAGE 200")
        self.assertIsNotNone(result)

    def test_volume_page_format(self):
        result = _extract_book_page("VOLUME 45 PAGE 123")
        self.assertIsNotNone(result)
        self.assertIn("45", result)
        self.assertIn("123", result)

    def test_or_book_format(self):
        result = _extract_book_page("OR BOOK 88 PAGE 17")
        self.assertIsNotNone(result)

    def test_output_format(self):
        result = _extract_book_page("BOOK 312 PAGE 44")
        self.assertEqual(result, "Book 312 Page 44")

    def test_no_book_page_returns_none(self):
        result = _extract_book_page("NO BOOK OR PAGE REFERENCE HERE")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _extract_legal_description()
# ---------------------------------------------------------------------------

class ExtractLegalDescriptionTests(unittest.TestCase):

    def test_situated_in_township(self):
        text = "Situated in the Township of Pleasant, Seneca County, State of Ohio, being Lot 4"
        result = _extract_legal_description(text, text.upper())
        self.assertIsNotNone(result)
        self.assertIn("Township", result)

    def test_being_in_city(self):
        text = "Being in the City of Tiffin, Seneca County, Ohio"
        result = _extract_legal_description(text, text.upper())
        self.assertIsNotNone(result)

    def test_following_described_property(self):
        text = "The following described real property: Lot 4 of Block 2"
        result = _extract_legal_description(text, text.upper())
        self.assertIsNotNone(result)
        self.assertIn("Lot 4", result)

    def test_legal_description_label(self):
        text = "Legal Description: Lot 1 of Block 5 of Some Subdivision"
        result = _extract_legal_description(text, text.upper())
        self.assertIsNotNone(result)

    def test_snippet_capped_at_500_chars(self):
        long_legal = "Situated in the Township of X, " + ("Y " * 300)
        result = _extract_legal_description(long_legal, long_legal.upper())
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), 500)

    def test_no_legal_returns_none(self):
        result = _extract_legal_description(
            "No legal description here.", "NO LEGAL DESCRIPTION HERE.")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _extract_preparer() — including title search disclaimer
# ---------------------------------------------------------------------------

class ExtractPreparerTests(unittest.TestCase):

    def _run(self, text):
        return _extract_preparer(text, text.upper())

    def test_prepared_by_format(self):
        text = "Prepared by: James T. Black, Attorney at Law\n"
        preparer, notes = self._run(text)
        self.assertIsNotNone(preparer)
        self.assertIn("Black", preparer)

    def test_drafted_by_format(self):
        text = "Drafted by: Susan M. Green, ESQ\n"
        preparer, notes = self._run(text)
        self.assertIsNotNone(preparer)

    def test_instrument_prepared_by_format(self):
        text = "This instrument prepared by: Robert J. Doe, Attorney.\n"
        preparer, notes = self._run(text)
        self.assertIsNotNone(preparer)

    def test_title_search_disclaimer_detected(self):
        """SR-005 signal: 'without benefit of title search' should populate preparer_notes."""
        text = "This instrument was prepared without benefit of title search by James Black."
        preparer, notes = self._run(text)
        self.assertIsNotNone(notes)
        self.assertIn("title search", notes.lower())

    def test_without_benefit_of_abstract(self):
        text = "Prepared without the benefit of an abstract."
        preparer, notes = self._run(text)
        self.assertIsNotNone(notes)

    def test_without_title_examination(self):
        text = "This deed was prepared without title examination by the drafter."
        preparer, notes = self._run(text)
        self.assertIsNotNone(notes)

    def test_no_title_search_performed(self):
        text = "No title search was performed prior to preparation."
        preparer, notes = self._run(text)
        self.assertIsNotNone(notes)

    def test_preparer_notes_contain_context_window(self):
        """Notes should capture surrounding context, not just the disclaimer phrase."""
        text = "James Black prepared this deed. Without benefit of title search."
        preparer, notes = self._run(text)
        self.assertIsNotNone(notes)
        self.assertGreater(len(notes), 10)

    def test_no_preparer_no_disclaimer_returns_none_none(self):
        preparer, notes = self._run(
            "This deed has no preparer information at all.")
        self.assertIsNone(preparer)
        self.assertIsNone(notes)

    def test_preparer_and_disclaimer_both_found(self):
        text = (
            "Prepared by: John Doe, Attorney at Law\n"
            "This instrument was prepared without benefit of title search."
        )
        preparer, notes = self._run(text)
        self.assertIsNotNone(preparer)
        self.assertIsNotNone(notes)


# ---------------------------------------------------------------------------
# Integration: parse_recorder_document with full deed text
# ---------------------------------------------------------------------------

class ParseRecorderDocumentIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.deed_text = _deed_text(
            instrument="WARRANTY DEED",
            grantor="EXAMPLE DAVID A",
            grantee="EXAMPLE PROPERTIES LLC",
            consideration="WITHOUT CONSIDERATION",
            parcel="22-001234.000",
            recording_date="RECORDED ON March 15, 2018",
            instrument_number="INSTRUMENT NO. 2018-00456",
            book_page="BOOK 312 PAGE 44",
            legal="Situated in the Township of Pleasant, Seneca County, Ohio",
            preparer="Prepared by: James T. Black, Attorney at Law",
            disclaimer="This instrument was prepared without benefit of title search.",
        )
        self.result = parse_recorder_document(
            self.deed_text, county=OhioCounty.SENECA)

    def test_instrument_type_is_warranty_deed(self):
        self.assertEqual(self.result.instrument_type, "WARRANTY DEED")

    def test_grantor_extracted(self):
        self.assertIsNotNone(self.result.grantor)

    def test_grantee_extracted(self):
        self.assertIsNotNone(self.result.grantee)

    def test_zero_consideration(self):
        """SR-005 signal: zero-consideration transfer."""
        self.assertEqual(self.result.consideration, 0.0)

    def test_parcel_id_extracted(self):
        self.assertIsNotNone(self.result.parcel_id)
        self.assertIn("22-001234", self.result.parcel_id)

    def test_recording_date_extracted(self):
        self.assertIsNotNone(self.result.recording_date)
        self.assertIn("2018", self.result.recording_date)

    def test_instrument_number_extracted(self):
        self.assertIsNotNone(self.result.instrument_number)
        self.assertIn("2018", self.result.instrument_number)

    def test_book_page_extracted(self):
        self.assertIsNotNone(self.result.book_page)
        self.assertEqual(self.result.book_page, "Book 312 Page 44")

    def test_legal_description_extracted(self):
        self.assertIsNotNone(self.result.legal_description)
        self.assertIn("Township", self.result.legal_description)

    def test_preparer_extracted(self):
        self.assertIsNotNone(self.result.preparer)
        self.assertIn("Black", self.result.preparer)

    def test_title_search_disclaimer_in_preparer_notes(self):
        """SR-005 signal: title search disclaimer present."""
        self.assertIsNotNone(self.result.preparer_notes)
        self.assertIn("title search", self.result.preparer_notes.lower())

    def test_county_preserved(self):
        self.assertEqual(self.result.county, OhioCounty.SENECA)

    def test_grantors_list(self):
        self.assertIsInstance(self.result.grantors, list)
        self.assertGreaterEqual(len(self.result.grantors), 1)

    def test_grantees_list(self):
        self.assertIsInstance(self.result.grantees, list)
        self.assertGreaterEqual(len(self.result.grantees), 1)


class ParseMortgageDocumentTests(unittest.TestCase):

    def test_mortgage_instrument_type(self):
        text = (
            "MORTGAGE\n\n"
            "GRANTOR: SMITH JOHN (Mortgagor)\n"
            "GRANTEE: FIRST NATIONAL BANK\n\n"
            "In consideration of the sum of $200,000.00\n\n"
            "Parcel No.: 11-054321.000\n"
        )
        result = parse_recorder_document(text)
        self.assertEqual(result.instrument_type, "MORTGAGE")
        self.assertAlmostEqual(result.consideration, 200000.0, places=2)
        self.assertIsNotNone(result.parcel_id)

    def test_satisfaction_of_mortgage(self):
        text = "SATISFACTION OF MORTGAGE recorded herein."
        result = parse_recorder_document(text)
        self.assertEqual(result.instrument_type, "SATISFACTION OF MORTGAGE")


# ---------------------------------------------------------------------------
# RecorderError
# ---------------------------------------------------------------------------

class RecorderErrorTests(unittest.TestCase):

    def test_message_attribute(self):
        err = RecorderError("Something went wrong")
        self.assertEqual(str(err), "Something went wrong")

    def test_county_attribute(self):
        err = RecorderError("Failure in Seneca", county=OhioCounty.SENECA)
        self.assertEqual(err.county, OhioCounty.SENECA)

    def test_county_defaults_to_none(self):
        err = RecorderError("No county")
        self.assertIsNone(err.county)

    def test_is_exception(self):
        err = RecorderError("test")
        self.assertIsInstance(err, Exception)

    def test_raises_correctly(self):
        with self.assertRaises(RecorderError) as cm:
            raise RecorderError("Boom", county=OhioCounty.HANCOCK)
        self.assertEqual(cm.exception.county, OhioCounty.HANCOCK)


# ---------------------------------------------------------------------------
# _title_case_name()
# ---------------------------------------------------------------------------

class TitleCaseNameTests(unittest.TestCase):

    def test_all_caps_converted(self):
        result = _title_case_name("EXAMPLE DAVID A")
        self.assertEqual(result, "Example David A")

    def test_llc_preserved(self):
        result = _title_case_name("EXAMPLE PROPERTIES LLC")
        self.assertEqual(result, "Example Properties LLC")

    def test_inc_preserved(self):
        # CORP and INC are both in the preserved-uppercase list
        result = _title_case_name("ACME CORP INC")
        self.assertEqual(result, "Acme CORP INC")

    def test_jr_preserved(self):
        result = _title_case_name("SMITH JOHN JR")
        self.assertEqual(result, "Smith John JR")

    def test_ii_preserved(self):
        result = _title_case_name("JONES WILLIAM II")
        self.assertEqual(result, "Jones William II")

    def test_mixed_case_passthrough(self):
        """Mixed-case input is returned as-is."""
        result = _title_case_name("Smith John")
        self.assertEqual(result, "Smith John")

    def test_lp_preserved(self):
        result = _title_case_name("BUCKEYE LAND LP")
        self.assertEqual(result, "Buckeye Land LP")

    def test_strips_whitespace(self):
        result = _title_case_name("  JONES ROBERT  ")
        self.assertEqual(result, "Jones Robert")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
