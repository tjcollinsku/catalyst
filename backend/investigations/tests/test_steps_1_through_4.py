"""
Verification tests for Steps 1–4 (Session 23).

These tests verify everything that can be tested without a live PostgreSQL
database: URL resolution, import integrity, serializer validation logic,
middleware behaviour, and view-level HTTP validation.
"""

import json
from unittest.mock import MagicMock

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

# ---------------------------------------------------------------------------
# 1.  URL resolution — all new endpoints resolve to the correct view
# ---------------------------------------------------------------------------


class UrlResolutionTests(SimpleTestCase):
    """Verify every URL pattern resolves to the expected view function."""

    def test_search_url(self):
        match = resolve("/api/search/")
        self.assertEqual(match.func.__name__, "api_search")

    def test_entity_detail_url(self):
        match = resolve("/api/entities/person/00000000-0000-0000-0000-000000000001/")
        self.assertEqual(match.func.__name__, "api_entity_detail")
        self.assertEqual(match.kwargs["entity_type"], "person")

    def test_case_export_url(self):
        match = resolve("/api/cases/00000000-0000-0000-0000-000000000001/export/")
        self.assertEqual(match.func.__name__, "api_case_export")

    def test_case_note_collection_url(self):
        match = resolve("/api/cases/00000000-0000-0000-0000-000000000001/notes/")
        self.assertEqual(match.func.__name__, "api_case_note_collection")

    def test_case_note_detail_url(self):
        match = resolve(
            "/api/cases/00000000-0000-0000-0000-000000000001/notes/00000000-0000-0000-0000-000000000002/"
        )
        self.assertEqual(match.func.__name__, "api_case_note_detail")

    def test_case_finding_collection_url(self):
        match = resolve("/api/cases/00000000-0000-0000-0000-000000000001/findings/")
        self.assertEqual(match.func.__name__, "api_case_finding_collection")

    def test_case_finding_detail_url(self):
        match = resolve(
            "/api/cases/00000000-0000-0000-0000-000000000001/findings/00000000-0000-0000-0000-000000000002/"
        )
        self.assertEqual(match.func.__name__, "api_case_finding_detail")


# ---------------------------------------------------------------------------
# 2.  Import integrity — all new symbols import cleanly
# ---------------------------------------------------------------------------


class ImportIntegrityTests(SimpleTestCase):
    """Verify that new code imports without error."""

    def test_views_import(self):
        from investigations import views

        # Check new view functions exist
        self.assertTrue(callable(views.api_search))
        self.assertTrue(callable(views.api_case_export))
        self.assertTrue(callable(views.api_entity_detail))
        self.assertTrue(callable(views.api_case_note_collection))
        self.assertTrue(callable(views.api_case_note_detail))
        self.assertTrue(callable(views.api_case_finding_collection))
        self.assertTrue(callable(views.api_case_finding_detail))

    def test_serializers_import(self):
        from investigations.serializers import (
            serialize_finding,
            serialize_note,
        )

        self.assertTrue(callable(serialize_finding))
        self.assertTrue(callable(serialize_note))

    def test_middleware_import(self):
        from investigations.middleware import TokenAuthMiddleware

        self.assertTrue(callable(TokenAuthMiddleware))

    def test_postgres_search_import(self):
        """Ensure the PG full-text search imports are present in views."""
        import inspect

        from investigations import views

        source = inspect.getsource(views)
        self.assertIn("SearchVector", source)
        self.assertIn("SearchQuery", source)
        self.assertIn("SearchRank", source)


# ---------------------------------------------------------------------------
# 3.  Search response shape (Step 1 verification)
# ---------------------------------------------------------------------------


class SearchResponseShapeTests(SimpleTestCase):
    """Verify the search view returns the correct field names."""

    def _get_search_view_source(self):
        import inspect

        from investigations import views

        return inspect.getsource(views.api_search)

    def test_uses_relevance_not_score(self):
        src = self._get_search_view_source()
        self.assertIn('"relevance"', src)
        self.assertNotIn('"score"', src)

    def test_uses_route_not_url(self):
        src = self._get_search_view_source()
        self.assertIn('"route"', src)
        # "url" might appear in other contexts (like docstrings), so check
        # specifically that results don't use "url" as a key
        self.assertNotIn('"url": f"/', src)

    def test_includes_subtitle_field(self):
        src = self._get_search_view_source()
        self.assertIn('"subtitle"', src)

    def test_includes_ai_overview_field(self):
        src = self._get_search_view_source()
        self.assertIn('"ai_overview"', src)


# ---------------------------------------------------------------------------
# 4.  Export response shape (Step 1 verification)
# ---------------------------------------------------------------------------


class ExportResponseShapeTests(SimpleTestCase):
    """Verify the export view returns {format, filename, download_url}."""

    def _get_export_view_source(self):
        import inspect

        from investigations import views

        return inspect.getsource(views.api_case_export)

    def test_returns_format_key(self):
        src = self._get_export_view_source()
        self.assertIn('"format"', src)

    def test_returns_filename_key(self):
        src = self._get_export_view_source()
        self.assertIn('"filename"', src)

    def test_returns_download_url_key(self):
        src = self._get_export_view_source()
        self.assertIn('"download_url"', src)

    def test_no_content_disposition(self):
        """Export should return JSON metadata, not a file download."""
        src = self._get_export_view_source()
        self.assertNotIn("Content-Disposition", src)


# ---------------------------------------------------------------------------
# 5.  Finding serializer validation (Step 4)
# ---------------------------------------------------------------------------


class FindingIntakeSerializerTests(SimpleTestCase):
    """Validate the FindingIntakeSerializer logic."""

    def _make_serializer(self, data):
        from investigations.serializers import FindingIntakeSerializer

        mock_case = MagicMock()
        return FindingIntakeSerializer(data=data, case=mock_case)

    def test_valid_minimal(self):
        s = self._make_serializer({"title": "Test Finding", "narrative": "Some narrative."})
        self.assertTrue(s.is_valid())

    def test_missing_title(self):
        s = self._make_serializer({"narrative": "Some narrative."})
        self.assertFalse(s.is_valid())
        self.assertIn("title", s.errors)

    def test_missing_narrative(self):
        s = self._make_serializer({"title": "Test"})
        self.assertFalse(s.is_valid())
        self.assertIn("narrative", s.errors)

    def test_invalid_severity(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "severity": "MEGA_BAD",
            }
        )
        self.assertFalse(s.is_valid())
        self.assertIn("severity", s.errors)

    def test_valid_severity(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "severity": "HIGH",
            }
        )
        self.assertTrue(s.is_valid())

    def test_invalid_confidence(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "confidence": "MAYBE",
            }
        )
        self.assertFalse(s.is_valid())
        self.assertIn("confidence", s.errors)

    def test_invalid_status(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "status": "PUBLISHED",
            }
        )
        self.assertFalse(s.is_valid())
        self.assertIn("status", s.errors)

    def test_unexpected_fields(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "foo": "bar",
            }
        )
        self.assertFalse(s.is_valid())
        self.assertIn("__all__", s.errors)

    def test_legal_refs_must_be_list(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "legal_refs": "not a list",
            }
        )
        self.assertFalse(s.is_valid())
        self.assertIn("legal_refs", s.errors)

    def test_valid_legal_refs(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "legal_refs": ["18 U.S.C. § 1343", "ORC 2913.02"],
            }
        )
        self.assertTrue(s.is_valid())

    def test_invalid_detection_id(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "detection_id": "not-a-uuid",
            }
        )
        self.assertFalse(s.is_valid())
        self.assertIn("detection_id", s.errors)

    def test_valid_detection_id(self):
        s = self._make_serializer(
            {
                "title": "Test",
                "narrative": "Text",
                "detection_id": "00000000-0000-0000-0000-000000000001",
            }
        )
        self.assertTrue(s.is_valid())


class FindingUpdateSerializerTests(SimpleTestCase):
    """Validate the FindingUpdateSerializer logic."""

    def _make_serializer(self, data):
        from investigations.serializers import FindingUpdateSerializer

        mock_instance = MagicMock()
        return FindingUpdateSerializer(data=data, instance=mock_instance)

    def test_valid_partial_update(self):
        s = self._make_serializer({"title": "Updated Title"})
        self.assertTrue(s.is_valid())

    def test_empty_body_rejected(self):
        s = self._make_serializer({})
        self.assertFalse(s.is_valid())

    def test_empty_title_rejected(self):
        s = self._make_serializer({"title": ""})
        self.assertFalse(s.is_valid())
        self.assertIn("title", s.errors)

    def test_empty_narrative_rejected(self):
        s = self._make_serializer({"narrative": "   "})
        self.assertFalse(s.is_valid())
        self.assertIn("narrative", s.errors)

    def test_invalid_severity(self):
        s = self._make_serializer({"severity": "UNKNOWN"})
        self.assertFalse(s.is_valid())
        self.assertIn("severity", s.errors)

    def test_unexpected_fields(self):
        s = self._make_serializer({"title": "OK", "bogus": True})
        self.assertFalse(s.is_valid())
        self.assertIn("__all__", s.errors)


# ---------------------------------------------------------------------------
# 6.  Middleware tests (Step 3)
# ---------------------------------------------------------------------------


class TokenAuthMiddlewareTests(SimpleTestCase):
    """Test the TokenAuthMiddleware in isolation."""

    def _make_middleware(self, tokens=None, require_auth=False):
        from investigations.middleware import TokenAuthMiddleware

        mock_get_response = MagicMock(return_value=MagicMock(status_code=200))

        with self.settings(
            CATALYST_API_TOKENS=set(tokens or []),
            CATALYST_REQUIRE_AUTH=require_auth,
        ):
            mw = TokenAuthMiddleware(mock_get_response)
        return mw, mock_get_response

    def _make_request(self, path="/api/cases/", auth_header=None):
        factory = RequestFactory()
        request = factory.get(path)
        if auth_header:
            request.META["HTTP_AUTHORIZATION"] = auth_header
        return request

    def test_no_tokens_configured_passes_through(self):
        """When CATALYST_API_TOKENS is empty, all requests pass through."""
        mw, get_response = self._make_middleware(tokens=[])
        request = self._make_request()
        _response = mw(request)
        get_response.assert_called_once_with(request)

    def test_valid_token_passes(self):
        mw, get_response = self._make_middleware(tokens=["my-secret-token"])
        request = self._make_request(auth_header="Bearer my-secret-token")
        _response = mw(request)
        get_response.assert_called_once_with(request)
        self.assertEqual(request.api_token, "my-secret-token")

    def test_missing_auth_header_returns_401(self):
        mw, _ = self._make_middleware(tokens=["my-secret-token"])
        request = self._make_request()
        response = mw(request)
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_returns_401(self):
        mw, _ = self._make_middleware(tokens=["my-secret-token"])
        request = self._make_request(auth_header="Bearer wrong-token")
        response = mw(request)
        self.assertEqual(response.status_code, 401)

    def test_bad_format_returns_401(self):
        mw, _ = self._make_middleware(tokens=["my-secret-token"])
        request = self._make_request(auth_header="Basic my-secret-token")
        response = mw(request)
        self.assertEqual(response.status_code, 401)

    def test_non_api_path_bypasses_auth(self):
        """Non-/api/ paths should not require authentication."""
        mw, get_response = self._make_middleware(tokens=["my-secret-token"])
        request = self._make_request(path="/admin/")
        _response = mw(request)
        get_response.assert_called_once_with(request)

    def test_require_auth_with_empty_tokens(self):
        """CATALYST_REQUIRE_AUTH=True + empty tokens → always 401 on /api/."""
        mw, _ = self._make_middleware(tokens=[], require_auth=True)
        request = self._make_request(auth_header="Bearer anything")
        response = mw(request)
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# 7.  HTTP-level validation (requires Django test client but no real DB)
# ---------------------------------------------------------------------------


class SearchValidationTests(SimpleTestCase):
    """Test search endpoint validation (no DB needed for these)."""

    def setUp(self):
        import django.conf

        django.conf.settings.ALLOWED_HOSTS = ["*"]

    def test_short_query_rejected(self):
        response = self.client.get("/api/search/?q=a")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("q", data["errors"])

    def test_invalid_type_rejected(self):
        response = self.client.get("/api/search/?q=test&type=invalid")
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("type", data["errors"])

    def test_export_view_exists_and_validates_format(self):
        """Verify the export view validates format before querying the DB."""
        import inspect

        from investigations import views

        src = inspect.getsource(views.api_case_export)
        # Format validation should happen (the view checks for json/csv)
        self.assertIn('"json"', src)
        self.assertIn('"csv"', src)
        self.assertIn("Invalid format", src)


# ---------------------------------------------------------------------------
# 8.  FINDING_SORT_FIELDS and URL count sanity checks
# ---------------------------------------------------------------------------


class FindingViewConfigTests(SimpleTestCase):
    """Verify Finding view configuration."""

    def test_finding_sort_fields_exist(self):
        from investigations.views import FINDING_SORT_FIELDS

        self.assertIn("created_at", FINDING_SORT_FIELDS)
        self.assertIn("severity", FINDING_SORT_FIELDS)
        self.assertIn("status", FINDING_SORT_FIELDS)
        self.assertIn("title", FINDING_SORT_FIELDS)

    def test_url_patterns_count(self):
        """We should now have at least 30 URL patterns (28 + 2 new finding paths)."""
        from investigations.urls import urlpatterns

        self.assertGreaterEqual(len(urlpatterns), 30)


# ---------------------------------------------------------------------------
# 9.  Settings verification (middleware registered, token config exists)
# ---------------------------------------------------------------------------


class SettingsVerificationTests(SimpleTestCase):
    """Verify settings are configured correctly."""

    def test_middleware_registered(self):
        from django.conf import settings

        self.assertIn(
            "investigations.middleware.TokenAuthMiddleware",
            settings.MIDDLEWARE,
        )

    def test_token_settings_exist(self):
        from django.conf import settings

        self.assertTrue(hasattr(settings, "CATALYST_API_TOKENS"))
        self.assertTrue(hasattr(settings, "CATALYST_REQUIRE_AUTH"))

    def test_default_tokens_empty(self):
        """By default, auth is disabled (empty token set)."""
        from django.conf import settings

        self.assertEqual(len(settings.CATALYST_API_TOKENS), 0)
