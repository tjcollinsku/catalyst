"""
Tests for county_auditor_connector.py

Coverage:
    - OhioCounty enum: all 88 counties present
    - AuditorPortalSystem enum: 3 systems
    - Registry completeness: all 88 counties, valid portal URLs, system assignments
    - get_auditor_info(): known county assertions, missing-county error path
    - list_counties(): total count, system filter, alphabetical sort
    - get_auditor_url(): Beacon URL, county-site URL, requires_login always False,
                        name/parcel hints in instructions
    - search_parcels_by_owner(): HTTP mocked — success, cross-county, county filter,
                                 empty query error, HTTP 500, timeout,
                                 connection error, JSON parse error, ArcGIS error,
                                 truncation flag
    - search_parcels_by_pin(): HTTP mocked — success, empty pin error
    - _parse_parcel_feature(): field extraction, None handling
    - _escape_like(): single-quote escaping
    - _build_result_note(): truncated/non-truncated, county/no-county scope
    - AuditorError: message, county, status_code attributes
    - ParcelRecord: dataclass defaults
    - ParcelSearchResult: dataclass fields

Run:
    python -m unittest investigations.tests_county_auditor -v
"""

import unittest
from unittest.mock import MagicMock

from investigations.county_auditor_connector import (
    _AUDITOR_REGISTRY,
    MAX_RESULTS,
    AuditorError,
    AuditorInfo,
    AuditorPortalSystem,
    AuditorUrlResult,
    OhioCounty,
    ParcelRecord,
    ParcelSearchResult,
    _build_result_note,
    _escape_like,
    _parse_parcel_feature,
    get_auditor_info,
    get_auditor_url,
    list_counties,
    search_parcels_by_owner,
    search_parcels_by_pin,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int = 200,
    json_data: dict | None = None,
    raise_for: type | None = None,
):
    """Build a mock requests.Response."""

    mock = MagicMock()
    mock.status_code = status_code

    if raise_for is not None:
        mock.json.side_effect = raise_for("mock error")
    elif json_data is not None:
        mock.json.return_value = json_data
    else:
        mock.json.return_value = {"features": []}

    return mock


def _sample_feature(
    objectid: int = 1,
    pin: str = "22-001234.000",
    statewide_pin: str = "OH-SENECA-22-001234",
    county: str = "SENECA",
    owner1: str = "EXAMPLE DAVID A",
    owner2: str = None,
    calc_acres: float = 5.2,
    assr_acres: float = 5.0,
    aud_link: str = "https://senecacountyauditoroh.gov/parcel/22-001234",
) -> dict:
    """Build a minimal ArcGIS feature dict for testing."""
    return {
        "attributes": {
            "OBJECTID": objectid,
            "PIN": pin,
            "STATEWIDE_PIN": statewide_pin,
            "COUNTY": county,
            "OWNER1": owner1,
            "OWNER2": owner2,
            "CALC_ACRES": calc_acres,
            "ASSR_ACRES": assr_acres,
            "AUD_LINK": aud_link,
        }
    }


def _api_response(features: list | None = None) -> dict:
    """Build a minimal ArcGIS API success response."""
    return {"features": features or []}


# ---------------------------------------------------------------------------
# OhioCounty enum
# ---------------------------------------------------------------------------


class OhioCountyEnumTests(unittest.TestCase):
    def test_all_88_counties_present(self):
        self.assertEqual(len(OhioCounty), 88)

    def test_darke_value(self):
        self.assertEqual(OhioCounty.DARKE.value, "darke")

    def test_mercer_value(self):
        self.assertEqual(OhioCounty.MERCER.value, "mercer")

    def test_seneca_value(self):
        self.assertEqual(OhioCounty.SENECA.value, "seneca")

    def test_all_values_lowercase(self):
        for county in OhioCounty:
            self.assertEqual(county.value, county.value.lower())

    def test_van_wert_has_underscore(self):
        self.assertEqual(OhioCounty.VAN_WERT.value, "van_wert")


# ---------------------------------------------------------------------------
# AuditorPortalSystem enum
# ---------------------------------------------------------------------------


class AuditorPortalSystemEnumTests(unittest.TestCase):
    def test_three_systems(self):
        self.assertEqual(len(AuditorPortalSystem), 3)

    def test_beacon_value(self):
        self.assertEqual(AuditorPortalSystem.BEACON.value, "Beacon (Schneider)")

    def test_county_site_value(self):
        self.assertEqual(AuditorPortalSystem.COUNTY_SITE.value, "County-Hosted Portal")

    def test_unavailable_value(self):
        self.assertEqual(AuditorPortalSystem.UNAVAILABLE.value, "In-Person/Phone Only")


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


class RegistryCompletenessTests(unittest.TestCase):
    def test_registry_has_88_entries(self):
        self.assertEqual(len(_AUDITOR_REGISTRY), 88)

    def test_every_ohio_county_in_registry(self):
        for county in OhioCounty:
            self.assertIn(county, _AUDITOR_REGISTRY, f"{county.name} missing")

    def test_all_entries_are_auditor_info(self):
        for county, info in _AUDITOR_REGISTRY.items():
            self.assertIsInstance(info, AuditorInfo)

    def test_all_beacon_counties_have_app_code(self):
        for county, info in _AUDITOR_REGISTRY.items():
            if info.system == AuditorPortalSystem.BEACON:
                self.assertIsNotNone(
                    info.beacon_app, f"{county.name} is Beacon but has no beacon_app"
                )
                self.assertIn(
                    "OH", info.beacon_app, f"{county.name} beacon_app should contain 'OH'"
                )

    def test_all_county_site_counties_have_no_beacon_app(self):
        for county, info in _AUDITOR_REGISTRY.items():
            if info.system == AuditorPortalSystem.COUNTY_SITE:
                self.assertIsNone(
                    info.beacon_app, f"{county.name} is COUNTY_SITE but has beacon_app set"
                )

    def test_all_entries_have_portal_url(self):
        for county, info in _AUDITOR_REGISTRY.items():
            if info.system != AuditorPortalSystem.UNAVAILABLE:
                self.assertIsNotNone(info.portal_url, f"{county.name} missing portal_url")
                self.assertTrue(
                    info.portal_url.startswith("https://"),
                    f"{county.name} portal_url should be https",
                )

    def test_all_entries_have_phone(self):
        for county, info in _AUDITOR_REGISTRY.items():
            self.assertTrue(info.phone, f"{county.name} missing phone")

    def test_all_entries_have_address(self):
        for county, info in _AUDITOR_REGISTRY.items():
            self.assertTrue(info.address, f"{county.name} missing address")

    def test_all_entries_have_portal_notes(self):
        for county, info in _AUDITOR_REGISTRY.items():
            self.assertTrue(info.portal_notes, f"{county.name} missing portal_notes")

    def test_all_fips_codes_are_odd(self):
        for county, info in _AUDITOR_REGISTRY.items():
            fips = int(info.fips)
            self.assertEqual(fips % 2, 1, f"{county.name} FIPS {fips} is even")
            self.assertTrue(1 <= fips <= 175, f"{county.name} FIPS out of range")

    # Known system assignments
    def test_darke_is_beacon(self):
        self.assertEqual(_AUDITOR_REGISTRY[OhioCounty.DARKE].system, AuditorPortalSystem.BEACON)

    def test_darke_beacon_app(self):
        self.assertEqual(_AUDITOR_REGISTRY[OhioCounty.DARKE].beacon_app, "DarkeCountyOH")

    def test_mercer_is_county_site(self):
        self.assertEqual(
            _AUDITOR_REGISTRY[OhioCounty.MERCER].system, AuditorPortalSystem.COUNTY_SITE
        )

    def test_mercer_portal_url(self):
        self.assertIn("mercercountyohio", _AUDITOR_REGISTRY[OhioCounty.MERCER].portal_url)

    def test_seneca_is_county_site(self):
        self.assertEqual(
            _AUDITOR_REGISTRY[OhioCounty.SENECA].system, AuditorPortalSystem.COUNTY_SITE
        )

    def test_seneca_portal_url(self):
        self.assertIn("seneca", _AUDITOR_REGISTRY[OhioCounty.SENECA].portal_url.lower())

    def test_franklin_is_county_site(self):
        self.assertEqual(
            _AUDITOR_REGISTRY[OhioCounty.FRANKLIN].system, AuditorPortalSystem.COUNTY_SITE
        )

    def test_hamilton_is_county_site(self):
        self.assertEqual(
            _AUDITOR_REGISTRY[OhioCounty.HAMILTON].system, AuditorPortalSystem.COUNTY_SITE
        )

    def test_cuyahoga_is_county_site(self):
        self.assertEqual(
            _AUDITOR_REGISTRY[OhioCounty.CUYAHOGA].system, AuditorPortalSystem.COUNTY_SITE
        )

    def test_allen_is_beacon(self):
        self.assertEqual(_AUDITOR_REGISTRY[OhioCounty.ALLEN].system, AuditorPortalSystem.BEACON)

    def test_wood_is_beacon(self):
        self.assertEqual(_AUDITOR_REGISTRY[OhioCounty.WOOD].system, AuditorPortalSystem.BEACON)

    def test_trumbull_is_county_site(self):
        self.assertEqual(
            _AUDITOR_REGISTRY[OhioCounty.TRUMBULL].system, AuditorPortalSystem.COUNTY_SITE
        )

    def test_beacon_counties_use_schneidercorp(self):
        for county, info in _AUDITOR_REGISTRY.items():
            if info.system == AuditorPortalSystem.BEACON:
                self.assertIn(
                    "schneidercorp.com",
                    info.portal_url,
                    f"{county.name} Beacon URL should use schneidercorp.com",
                )

    def test_majority_are_beacon(self):
        """Most Ohio counties use Beacon."""
        beacon = list_counties(system=AuditorPortalSystem.BEACON)
        self.assertGreater(len(beacon), 50)


# ---------------------------------------------------------------------------
# get_auditor_info()
# ---------------------------------------------------------------------------


class GetAuditorInfoTests(unittest.TestCase):
    def test_returns_auditor_info(self):
        info = get_auditor_info(OhioCounty.DARKE)
        self.assertIsInstance(info, AuditorInfo)

    def test_darke_name(self):
        info = get_auditor_info(OhioCounty.DARKE)
        self.assertEqual(info.name, "Darke")

    def test_darke_seat(self):
        info = get_auditor_info(OhioCounty.DARKE)
        self.assertEqual(info.seat, "Greenville")

    def test_mercer_fips(self):
        info = get_auditor_info(OhioCounty.MERCER)
        self.assertEqual(info.fips, "107")

    def test_seneca_phone(self):
        info = get_auditor_info(OhioCounty.SENECA)
        self.assertIn("419", info.phone)

    def test_every_county_retrievable(self):
        for county in OhioCounty:
            info = get_auditor_info(county)
            self.assertIsInstance(info, AuditorInfo)

    def test_missing_county_raises_auditor_error(self):
        saved = _AUDITOR_REGISTRY.pop(OhioCounty.DARKE)
        try:
            with self.assertRaises(AuditorError) as cm:
                get_auditor_info(OhioCounty.DARKE)
            self.assertEqual(cm.exception.county, OhioCounty.DARKE)
        finally:
            _AUDITOR_REGISTRY[OhioCounty.DARKE] = saved


# ---------------------------------------------------------------------------
# list_counties()
# ---------------------------------------------------------------------------


class ListCountiesTests(unittest.TestCase):
    def test_returns_88_without_filter(self):
        self.assertEqual(len(list_counties()), 88)

    def test_all_ohiocounty_instances(self):
        for county in list_counties():
            self.assertIsInstance(county, OhioCounty)

    def test_alphabetical_sort(self):
        counties = list_counties()
        names = [_AUDITOR_REGISTRY[c].name for c in counties]
        self.assertEqual(names, sorted(names))

    def test_filter_beacon(self):
        beacon = list_counties(system=AuditorPortalSystem.BEACON)
        self.assertGreater(len(beacon), 50)
        for county in beacon:
            self.assertEqual(_AUDITOR_REGISTRY[county].system, AuditorPortalSystem.BEACON)

    def test_filter_county_site(self):
        sites = list_counties(system=AuditorPortalSystem.COUNTY_SITE)
        self.assertGreater(len(sites), 5)
        for county in sites:
            self.assertEqual(_AUDITOR_REGISTRY[county].system, AuditorPortalSystem.COUNTY_SITE)

    def test_filter_sums_to_88(self):
        total = sum(len(list_counties(system=s)) for s in AuditorPortalSystem)
        self.assertEqual(total, 88)

    def test_darke_in_beacon_list(self):
        self.assertIn(OhioCounty.DARKE, list_counties(system=AuditorPortalSystem.BEACON))

    def test_mercer_in_county_site_list(self):
        self.assertIn(OhioCounty.MERCER, list_counties(system=AuditorPortalSystem.COUNTY_SITE))

    def test_seneca_in_county_site_list(self):
        self.assertIn(OhioCounty.SENECA, list_counties(system=AuditorPortalSystem.COUNTY_SITE))


# ---------------------------------------------------------------------------
# get_auditor_url()
# ---------------------------------------------------------------------------


class GetAuditorUrlTests(unittest.TestCase):
    def test_returns_auditor_url_result(self):
        result = get_auditor_url(OhioCounty.DARKE)
        self.assertIsInstance(result, AuditorUrlResult)

    def test_darke_county_name(self):
        result = get_auditor_url(OhioCounty.DARKE)
        self.assertEqual(result.county_name, "Darke")

    def test_darke_county_enum(self):
        result = get_auditor_url(OhioCounty.DARKE)
        self.assertEqual(result.county, OhioCounty.DARKE)

    def test_darke_system_is_beacon(self):
        result = get_auditor_url(OhioCounty.DARKE)
        self.assertEqual(result.system, AuditorPortalSystem.BEACON)

    def test_beacon_url_contains_schneidercorp(self):
        result = get_auditor_url(OhioCounty.DARKE)
        self.assertIn("schneidercorp.com", result.url)

    def test_county_site_url(self):
        result = get_auditor_url(OhioCounty.MERCER)
        self.assertIn("mercercountyohio", result.url)

    def test_requires_login_always_false(self):
        """All Ohio county auditor portals are free public access."""
        for county in OhioCounty:
            result = get_auditor_url(county)
            self.assertFalse(result.requires_login, f"{county.name} should not require login")

    def test_owner_name_appears_in_instructions_for_beacon(self):
        result = get_auditor_url(OhioCounty.DARKE, owner_name="EXAMPLE")
        self.assertIn("EXAMPLE", result.instructions)

    def test_parcel_id_appears_in_instructions_for_beacon(self):
        result = get_auditor_url(OhioCounty.ALLEN, parcel_id="22-001234.000")
        self.assertIn("22-001234.000", result.instructions)

    def test_no_name_returns_standard_notes(self):
        result = get_auditor_url(OhioCounty.DARKE)
        self.assertTrue(result.instructions)

    def test_county_site_instructions_not_empty(self):
        result = get_auditor_url(OhioCounty.SENECA)
        self.assertTrue(result.instructions)

    def test_all_counties_have_url(self):
        for county in OhioCounty:
            info = _AUDITOR_REGISTRY[county]
            if info.system != AuditorPortalSystem.UNAVAILABLE:
                result = get_auditor_url(county)
                self.assertIsNotNone(result.url, f"{county.name} should have a URL")


# ---------------------------------------------------------------------------
# search_parcels_by_owner() — HTTP mocked
# ---------------------------------------------------------------------------


class SearchParcelsByOwnerTests(unittest.TestCase):
    def _mock_session(self, json_data: dict, status_code: int = 200):
        session = MagicMock()
        session.get.return_value = _make_response(status_code=status_code, json_data=json_data)
        return session

    def test_empty_query_raises(self):
        with self.assertRaises(AuditorError):
            search_parcels_by_owner("")

    def test_whitespace_query_raises(self):
        with self.assertRaises(AuditorError):
            search_parcels_by_owner("   ")

    def test_success_returns_parcel_search_result(self):
        session = self._mock_session(_api_response([_sample_feature()]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIsInstance(result, ParcelSearchResult)

    def test_success_count(self):
        session = self._mock_session(
            _api_response([_sample_feature(), _sample_feature(objectid=2, pin="22-002345.000")])
        )
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertEqual(result.count, 2)

    def test_success_records_list(self):
        session = self._mock_session(_api_response([_sample_feature()]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIsInstance(result.records, list)
        self.assertEqual(len(result.records), 1)

    def test_query_preserved(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertEqual(result.query, "EXAMPLE")

    def test_no_county_filter(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIsNone(result.county_filter)

    def test_county_filter_applied(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", county=OhioCounty.SENECA, session=session)
        self.assertEqual(result.county_filter, "seneca")

    def test_county_filter_in_where_clause(self):
        """County name should appear in the SQL WHERE clause sent to the API."""
        session = self._mock_session(_api_response([]))
        search_parcels_by_owner("EXAMPLE", county=OhioCounty.DARKE, session=session)
        call_args = session.get.call_args
        params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][1]
        self.assertIn("DARKE", params["where"].upper())

    def test_owner1_and_owner2_searched(self):
        """WHERE clause must search both OWNER1 and OWNER2."""
        session = self._mock_session(_api_response([]))
        search_parcels_by_owner("SMITH", session=session)
        call_args = session.get.call_args
        params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][1]
        self.assertIn("OWNER1", params["where"])
        self.assertIn("OWNER2", params["where"])

    def test_truncated_flag_when_max_results(self):
        features = [_sample_feature(objectid=i, pin=f"22-{i:06d}.000") for i in range(MAX_RESULTS)]
        session = self._mock_session(_api_response(features))
        result = search_parcels_by_owner("JONES", session=session)
        self.assertTrue(result.truncated)

    def test_not_truncated_when_under_max(self):
        features = [_sample_feature()]
        session = self._mock_session(_api_response(features))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertFalse(result.truncated)

    def test_http_500_raises_auditor_error(self):
        session = self._mock_session({}, status_code=500)
        with self.assertRaises(AuditorError) as cm:
            search_parcels_by_owner("EXAMPLE", session=session)
        self.assertEqual(cm.exception.status_code, 500)

    def test_http_404_raises_auditor_error(self):
        session = self._mock_session({}, status_code=404)
        with self.assertRaises(AuditorError) as cm:
            search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIsNotNone(cm.exception.status_code)

    def test_timeout_raises_auditor_error(self):
        import requests as req_lib

        session = MagicMock()
        session.get.side_effect = req_lib.exceptions.Timeout()
        with self.assertRaises(AuditorError) as cm:
            search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIn("timed out", str(cm.exception).lower())

    def test_connection_error_raises_auditor_error(self):
        import requests as req_lib

        session = MagicMock()
        session.get.side_effect = req_lib.exceptions.ConnectionError()
        with self.assertRaises(AuditorError):
            search_parcels_by_owner("EXAMPLE", session=session)

    def test_json_parse_error_raises_auditor_error(self):
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        session.get.return_value = mock_resp
        with self.assertRaises(AuditorError):
            search_parcels_by_owner("EXAMPLE", session=session)

    def test_arcgis_error_response_raises(self):
        session = self._mock_session({"error": {"code": 400, "message": "Invalid query"}})
        with self.assertRaises(AuditorError) as cm:
            search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIn("400", str(cm.exception))

    def test_empty_features_returns_zero_count(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("NOBODY", session=session)
        self.assertEqual(result.count, 0)
        self.assertEqual(result.records, [])

    def test_note_contains_query(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIn("EXAMPLE", result.note)

    def test_note_mentions_auditor_portal(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIn("auditor", result.note.lower())

    def test_cross_county_note_mentions_all_counties(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", session=session)
        self.assertIn("88", result.note)

    def test_county_filter_note_mentions_county(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_owner("EXAMPLE", county=OhioCounty.DARKE, session=session)
        self.assertIn("Darke", result.note)

    def test_query_url_is_odnr(self):
        """Verify the correct ODNR endpoint is called."""
        session = self._mock_session(_api_response([]))
        search_parcels_by_owner("EXAMPLE", session=session)
        call_url = session.get.call_args[0][0]
        self.assertIn("odnr_landbase_v2", call_url)

    def test_return_geometry_is_false(self):
        session = self._mock_session(_api_response([]))
        search_parcels_by_owner("EXAMPLE", session=session)
        params = session.get.call_args[1]["params"]
        self.assertEqual(params["returnGeometry"], "false")


# ---------------------------------------------------------------------------
# search_parcels_by_pin() — HTTP mocked
# ---------------------------------------------------------------------------


class SearchParcelsByPinTests(unittest.TestCase):
    def _mock_session(self, json_data: dict):
        session = MagicMock()
        session.get.return_value = _make_response(json_data=json_data)
        return session

    def test_empty_pin_raises(self):
        with self.assertRaises(AuditorError):
            search_parcels_by_pin("")

    def test_whitespace_pin_raises(self):
        with self.assertRaises(AuditorError):
            search_parcels_by_pin("   ")

    def test_success_returns_result(self):
        session = self._mock_session(_api_response([_sample_feature()]))
        result = search_parcels_by_pin("22-001234.000", session=session)
        self.assertIsInstance(result, ParcelSearchResult)

    def test_pin_preserved_in_query(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_pin("22-001234.000", session=session)
        self.assertEqual(result.query, "22-001234.000")

    def test_pin_in_where_clause(self):
        session = self._mock_session(_api_response([]))
        search_parcels_by_pin("22-001234", session=session)
        params = session.get.call_args[1]["params"]
        self.assertIn("22-001234", params["where"])

    def test_statewide_pin_searched(self):
        session = self._mock_session(_api_response([]))
        search_parcels_by_pin("22-001234", session=session)
        params = session.get.call_args[1]["params"]
        self.assertIn("STATEWIDE_PIN", params["where"])

    def test_county_filter_applied(self):
        session = self._mock_session(_api_response([]))
        result = search_parcels_by_pin("22-001234", county=OhioCounty.SENECA, session=session)
        self.assertEqual(result.county_filter, "seneca")


# ---------------------------------------------------------------------------
# _parse_parcel_feature()
# ---------------------------------------------------------------------------


class ParseParcelFeatureTests(unittest.TestCase):
    def test_all_fields_populated(self):
        feature = _sample_feature()
        record = _parse_parcel_feature(feature)
        self.assertEqual(record.object_id, 1)
        self.assertEqual(record.pin, "22-001234.000")
        self.assertEqual(record.statewide_pin, "OH-SENECA-22-001234")
        self.assertEqual(record.county, "SENECA")
        self.assertEqual(record.owner1, "EXAMPLE DAVID A")
        self.assertIsNone(record.owner2)
        self.assertAlmostEqual(record.calc_acres, 5.2, places=1)
        self.assertAlmostEqual(record.assr_acres, 5.0, places=1)
        self.assertIn("seneca", record.aud_link.lower())

    def test_raw_dict_preserved(self):
        feature = _sample_feature()
        record = _parse_parcel_feature(feature)
        self.assertIsInstance(record.raw, dict)
        self.assertIn("OBJECTID", record.raw)

    def test_none_owner2_stays_none(self):
        feature = _sample_feature(owner2=None)
        record = _parse_parcel_feature(feature)
        self.assertIsNone(record.owner2)

    def test_owner2_populated_when_present(self):
        feature = _sample_feature(owner2="EXAMPLE JANE B")
        record = _parse_parcel_feature(feature)
        self.assertEqual(record.owner2, "EXAMPLE JANE B")

    def test_empty_string_field_returns_none(self):
        feature = {"attributes": {"OBJECTID": 1, "PIN": "", "COUNTY": "  ", "OWNER1": "SMITH"}}
        record = _parse_parcel_feature(feature)
        self.assertIsNone(record.pin)
        self.assertIsNone(record.county)

    def test_missing_field_returns_none(self):
        feature = {"attributes": {"OBJECTID": 1}}
        record = _parse_parcel_feature(feature)
        self.assertIsNone(record.pin)
        self.assertIsNone(record.owner1)
        self.assertIsNone(record.calc_acres)

    def test_float_fields(self):
        feature = _sample_feature(calc_acres=10.75, assr_acres=10.5)
        record = _parse_parcel_feature(feature)
        self.assertAlmostEqual(record.calc_acres, 10.75, places=2)
        self.assertAlmostEqual(record.assr_acres, 10.5, places=2)

    def test_non_numeric_acres_returns_none(self):
        feature = {"attributes": {"CALC_ACRES": "n/a", "ASSR_ACRES": None}}
        record = _parse_parcel_feature(feature)
        self.assertIsNone(record.calc_acres)
        self.assertIsNone(record.assr_acres)


# ---------------------------------------------------------------------------
# _escape_like()
# ---------------------------------------------------------------------------


class EscapeLikeTests(unittest.TestCase):
    def test_no_quotes_unchanged(self):
        self.assertEqual(_escape_like("EXAMPLE"), "EXAMPLE")

    def test_single_quote_doubled(self):
        self.assertEqual(_escape_like("O'BRIEN"), "O''BRIEN")

    def test_multiple_quotes(self):
        self.assertEqual(_escape_like("O'BRIEN O'REILLY"), "O''BRIEN O''REILLY")

    def test_empty_string(self):
        self.assertEqual(_escape_like(""), "")

    def test_no_modification_for_safe_chars(self):
        self.assertEqual(_escape_like("SMITH 123-456"), "SMITH 123-456")


# ---------------------------------------------------------------------------
# _build_result_note()
# ---------------------------------------------------------------------------


class BuildResultNoteTests(unittest.TestCase):
    def test_contains_query(self):
        note = _build_result_note("EXAMPLE", None, 5, False)
        self.assertIn("EXAMPLE", note)

    def test_no_county_mentions_all_88(self):
        note = _build_result_note("EXAMPLE", None, 5, False)
        self.assertIn("88", note)

    def test_county_filter_mentioned(self):
        note = _build_result_note("EXAMPLE", "seneca", 3, False)
        self.assertIn("Seneca", note)

    def test_count_mentioned(self):
        note = _build_result_note("EXAMPLE", None, 7, False)
        self.assertIn("7", note)

    def test_truncated_note_warns(self):
        note = _build_result_note("JONES", None, MAX_RESULTS, True)
        self.assertIn(str(MAX_RESULTS), note)
        self.assertIn("refine", note.lower())

    def test_non_truncated_no_warning(self):
        note = _build_result_note("JONES", None, 5, False)
        self.assertNotIn("refine", note.lower())

    def test_note_mentions_auditor_portal(self):
        note = _build_result_note("EXAMPLE", None, 1, False)
        self.assertIn("auditor", note.lower())

    def test_note_mentions_sale_price(self):
        note = _build_result_note("EXAMPLE", None, 1, False)
        self.assertIn("sale price", note.lower())


# ---------------------------------------------------------------------------
# AuditorError
# ---------------------------------------------------------------------------


class AuditorErrorTests(unittest.TestCase):
    def test_message_attribute(self):
        err = AuditorError("Something went wrong")
        self.assertEqual(str(err), "Something went wrong")

    def test_county_attribute(self):
        err = AuditorError("Failed", county=OhioCounty.DARKE)
        self.assertEqual(err.county, OhioCounty.DARKE)

    def test_county_defaults_none(self):
        err = AuditorError("No county")
        self.assertIsNone(err.county)

    def test_status_code_attribute(self):
        err = AuditorError("HTTP error", status_code=500)
        self.assertEqual(err.status_code, 500)

    def test_status_code_defaults_none(self):
        err = AuditorError("No code")
        self.assertIsNone(err.status_code)

    def test_is_exception(self):
        self.assertIsInstance(AuditorError("test"), Exception)

    def test_raises_correctly(self):
        with self.assertRaises(AuditorError) as cm:
            raise AuditorError("Boom", county=OhioCounty.MERCER, status_code=404)
        self.assertEqual(cm.exception.county, OhioCounty.MERCER)
        self.assertEqual(cm.exception.status_code, 404)


# ---------------------------------------------------------------------------
# ParcelRecord dataclass
# ---------------------------------------------------------------------------


class ParcelRecordTests(unittest.TestCase):
    def test_default_fields_are_none(self):
        record = ParcelRecord()
        self.assertIsNone(record.object_id)
        self.assertIsNone(record.pin)
        self.assertIsNone(record.owner1)
        self.assertIsNone(record.calc_acres)

    def test_raw_defaults_empty_dict(self):
        record = ParcelRecord()
        self.assertEqual(record.raw, {})

    def test_fields_assignable(self):
        record = ParcelRecord(pin="22-001234.000", owner1="EXAMPLE DAVID A", county="SENECA")
        self.assertEqual(record.pin, "22-001234.000")
        self.assertEqual(record.owner1, "EXAMPLE DAVID A")
        self.assertEqual(record.county, "SENECA")


# ---------------------------------------------------------------------------
# ParcelSearchResult dataclass
# ---------------------------------------------------------------------------


class ParcelSearchResultTests(unittest.TestCase):
    def test_fields(self):
        result = ParcelSearchResult(
            query="EXAMPLE",
            county_filter="seneca",
            records=[],
            count=0,
            truncated=False,
            note="test note",
        )
        self.assertEqual(result.query, "EXAMPLE")
        self.assertEqual(result.county_filter, "seneca")
        self.assertEqual(result.records, [])
        self.assertEqual(result.count, 0)
        self.assertFalse(result.truncated)
        self.assertEqual(result.note, "test note")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
