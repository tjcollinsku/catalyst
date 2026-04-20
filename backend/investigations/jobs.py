"""Background task functions for async research jobs.

Each function takes a SearchJob id (string UUID), loads the row, runs
the corresponding connector, and writes the response payload or the
exception back to the row. These functions are enqueued via
django_q.tasks.async_task from the converted research views.

Task functions are plain Python callables — Django-Q2 imports them by
dotted path, so the name and location here matter. If you rename or
move one, update the enqueue calls in views.py too.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from investigations import (
    county_auditor_connector,
    irs_connector,
    ohio_aos_connector,
)
from investigations.models import JobStatus, SearchJob

logger = logging.getLogger(__name__)


def _load_and_mark_running(job_id: str) -> SearchJob | None:
    """Load a job by id, flip it to RUNNING, return it.

    Returns None if the job no longer exists (e.g. it was deleted between
    enqueue and pickup). Callers should bail out in that case.
    """
    try:
        job = SearchJob.objects.get(id=job_id)
    except SearchJob.DoesNotExist:
        logger.warning("SearchJob %s not found on pickup", job_id)
        return None

    job.status = JobStatus.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    return job


def _mark_success(job: SearchJob, result: dict) -> None:
    job.status = JobStatus.SUCCESS
    job.result = result
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "result", "finished_at"])


def _mark_failed(job: SearchJob, exc: BaseException) -> None:
    job.status = JobStatus.FAILED
    job.error_message = f"{type(exc).__name__}: {exc}"
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at"])
    logger.exception("SearchJob %s failed: %s", job.id, exc)


# ---------------------------------------------------------------------------
# IRS — name search (scan every index year)
# ---------------------------------------------------------------------------


def run_irs_name_search(job_id: str) -> None:
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        filings = irs_connector.search_990_by_name(
            query,
            years=irs_connector.INDEX_YEARS,
            max_results=200,
        )
        records = [irs_connector.filing_to_dict(f) for f in filings]
        result = {
            "source": "irs_teos_xml",
            "results": records,
            "count": len(records),
            "notes": [
                "City/state not shown in search — click Fetch 990 Data to pull "
                "address and full financial/governance detail from the XML."
            ],
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001 — surface every error to the user
        _mark_failed(job, exc)


# ---------------------------------------------------------------------------
# IRS — EIN search + fetch + parse XML
# ---------------------------------------------------------------------------


def run_irs_fetch_xml(job_id: str) -> None:
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        cleaned = query.replace("-", "").replace(" ", "")
        search_result = irs_connector.search_990_by_ein(
            cleaned, years=irs_connector.INDEX_YEARS
        )
        records = []
        notes = []
        for filing in search_result.filings:
            record = irs_connector.filing_to_dict(filing)
            try:
                xml_text = irs_connector.fetch_990_xml(filing)
                parsed = irs_connector.parse_990_xml(
                    xml_text, filing.object_id, filing.xml_batch_id
                )
                record["parsed"] = irs_connector.parsed_990_to_dict(parsed)
            except (
                irs_connector.IRSNetworkError,
                irs_connector.IRSParseError,
            ) as e:
                record["parsed"] = None
                notes.append(
                    f"Could not parse {filing.return_type} {filing.tax_year}: {e}"
                )
            records.append(record)

        if search_result.total_found == 0:
            notes.append(
                f"No e-filed 990 returns found for EIN "
                f"{search_result.ein_formatted} in "
                f"{', '.join(str(y) for y in search_result.years_searched)} "
                f"indexes. The organization may file on paper or be below the "
                f"e-filing threshold."
            )

        result = {
            "source": "irs_teos_xml",
            "results": records,
            "count": len(records),
            "notes": notes,
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(job, exc)


# ---------------------------------------------------------------------------
# Ohio AOS — audit report scrape
# ---------------------------------------------------------------------------


def _aos_report_to_dict(report) -> dict:
    return {
        "entity_name": report.entity_name,
        "county": report.county,
        "report_type": report.report_type,
        "entity_type": report.entity_type,
        "report_period": report.report_period,
        "release_date": (
            report.release_date.isoformat() if report.release_date else None
        ),
        "has_findings_for_recovery": report.has_findings_for_recovery,
        "pdf_url": report.pdf_url,
    }


def run_ohio_aos_search(job_id: str) -> None:
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        reports = ohio_aos_connector.search_audit_reports(query)
        records = [_aos_report_to_dict(r) for r in reports]
        result = {
            "source": "ohio_aos",
            "results": records,
            "count": len(records),
            "notes": [],
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(job, exc)


# ---------------------------------------------------------------------------
# County Auditor — ODNR parcel search
# ---------------------------------------------------------------------------


def _parcel_record_to_dict(record) -> dict:
    return {
        "pin": record.pin,
        "owner1": record.owner1,
        "owner2": record.owner2,
        "county": record.county,
        "acres_calc": record.calc_acres,
        "acres_desc": record.assr_acres,
        "aud_link": record.aud_link,
    }


def run_county_parcel_search(job_id: str) -> None:
    job = _load_and_mark_running(job_id)
    if job is None:
        return
    try:
        query = job.query_params["query"].strip()
        county_str = job.query_params.get("county") or ""
        search_type = (job.query_params.get("search_type") or "owner").lower()

        # Resolve county string to the OhioCounty enum (or None)
        county = None
        if county_str:
            try:
                county = county_auditor_connector.OhioCounty[
                    county_str.upper()
                ]
            except KeyError:
                _mark_failed(
                    job,
                    ValueError(
                        f"Invalid county: {county_str!r}. "
                        "Must be a valid Ohio county name."
                    ),
                )
                return

        if search_type == "parcel":
            result_obj = county_auditor_connector.search_parcels_by_pin(
                query, county=county
            )
        else:
            result_obj = county_auditor_connector.search_parcels_by_owner(
                query, county=county
            )

        records = [_parcel_record_to_dict(r) for r in result_obj.records]
        notes = [result_obj.note] if result_obj.note else []
        result = {
            "source": "county_auditor",
            "results": records,
            "count": len(records),
            "notes": notes,
        }
        _mark_success(job, result)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(job, exc)
