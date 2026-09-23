"""Data-quality checks over batches of resume records.

Answers three questions before any ranking happens: are the records valid, are
fields populated, and are any of them duplicates? Ranking a corpus that
silently contains the same person three times produces a confident, wrong
shortlist.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import pandas as pd
from pandas.api import types as pdtypes
from pydantic import ValidationError

from src.models.quality import DataQualityReport, DuplicateSummary, ValidationFailure
from src.models.resume import ResumeSchema

logger = logging.getLogger(__name__)

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$|^present$"


class DataQualityChecker:
    """Validate resume records and report on their quality."""

    def __init__(
        self,
        completeness_min: float = 80.0,
        duplicate_max: float = 5.0,
        validity_min: float = 90.0,
    ) -> None:
        """Configure the thresholds a batch is assessed against.

        Args:
            completeness_min: Minimum acceptable mean field completeness (%).
            duplicate_max: Maximum acceptable duplicate share (%).
            validity_min: Minimum acceptable share of valid records (%).
        """
        self.completeness_min = completeness_min
        self.duplicate_max = duplicate_max
        self.validity_min = validity_min

    def validate(
        self, records: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[ValidationFailure]]:
        """Split records into those that satisfy ``ResumeSchema`` and those that don't.

        Args:
            records: Raw resume dictionaries.

        Returns:
            A ``(valid, failures)`` pair. Each failure names the field, the
            message and the offending input, truncated.
        """
        valid: list[dict[str, Any]] = []
        failures: list[ValidationFailure] = []

        for index, record in enumerate(records):
            try:
                valid.append(ResumeSchema(**record).model_dump())
            except ValidationError as exc:
                failures.append(
                    ValidationFailure(
                        record_index=index,
                        record_id=str(record.get("id", f"record_{index}")),
                        errors=[
                            {
                                "field": ".".join(str(part) for part in error["loc"]),
                                "message": error["msg"],
                                "type": error["type"],
                                "input": str(error.get("input", "N/A"))[:100],
                            }
                            for error in exc.errors()
                        ],
                    )
                )
        return valid, failures

    def completeness(self, frame: pd.DataFrame) -> dict[str, float]:
        """Percentage of non-empty values per column.

        A whitespace-only string counts as missing: a field containing " " is
        absent in every sense that matters, and treating it as present inflates
        the score.
        """
        if frame.empty:
            return {}

        scores: dict[str, float] = {}
        for column in frame.columns:
            series = frame[column]
            if pdtypes.is_numeric_dtype(series) or pdtypes.is_bool_dtype(series):
                populated = series.notna()
            else:
                populated = series.notna() & (
                    series.astype(str).str.strip().ne("") & series.astype(str).str.strip().ne("[]")
                )
            scores[str(column)] = round(float(populated.sum()) / len(frame) * 100, 2)
        return scores

    def duplicates(self, frame: pd.DataFrame) -> DuplicateSummary:
        """Count duplicates by identity key and by whole-row content hash.

        Two passes because they catch different faults: the key pass finds the
        same person submitted twice, the content pass finds a record copied
        wholesale under a new id.
        """
        if frame.empty:
            return DuplicateSummary()

        key_columns = [column for column in ("name", "contact.email") if column in frame.columns]
        if key_columns:
            key_duplicates = int(frame.duplicated(subset=key_columns, keep=False).sum())
        else:
            key_duplicates = 0

        hashes = frame.apply(
            lambda row: hashlib.sha256(
                str(sorted(row.dropna().astype(str).to_dict().items())).encode("utf-8")
            ).hexdigest(),
            axis=1,
        )
        content_duplicates = int(hashes.duplicated().sum())

        return DuplicateSummary(
            key_duplicate_count=key_duplicates,
            content_duplicate_count=content_duplicates,
            duplicate_percentage=round(key_duplicates / len(frame) * 100, 2),
        )

    def consistency(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        """Flag values that parsed but do not match their expected format."""
        if frame.empty:
            return []

        issues: list[dict[str, Any]] = []

        if "contact.email" in frame.columns:
            invalid = ~frame["contact.email"].astype(str).str.match(EMAIL_PATTERN, na=False)
            if invalid.any():
                issues.append(
                    {
                        "issue": "invalid_email_format",
                        "count": int(invalid.sum()),
                        "percentage": round(float(invalid.sum()) / len(frame) * 100, 2),
                    }
                )

        for column in (col for col in frame.columns if "date" in str(col).lower()):
            values = frame[column].dropna()
            if values.empty:
                continue
            invalid = ~values.astype(str).str.match(DATE_PATTERN, na=False)
            if invalid.any():
                issues.append(
                    {
                        "issue": f"invalid_date_format:{column}",
                        "count": int(invalid.sum()),
                        "percentage": round(float(invalid.sum()) / len(values) * 100, 2),
                    }
                )

        return issues

    def report(self, records: list[dict[str, Any]]) -> DataQualityReport:
        """Run every check and assemble the report.

        Args:
            records: Raw resume dictionaries.

        Returns:
            The assembled report. Metrics are computed over the *valid*
            records only — completeness of records that failed validation is
            not a meaningful number.
        """
        valid, failures = self.validate(records)
        frame = pd.json_normalize(valid) if valid else pd.DataFrame()

        report = DataQualityReport(
            total_records=len(records),
            valid_records=len(valid),
            invalid_records=len(failures),
            completeness=self.completeness(frame),
            duplicates=self.duplicates(frame),
            consistency_issues=self.consistency(frame),
            failures=failures,
        )
        logger.info(
            "Quality report: %d/%d valid (%.1f%%), %d duplicates, %d consistency issues",
            report.valid_records,
            report.total_records,
            report.quality_score,
            report.duplicates.key_duplicate_count,
            len(report.consistency_issues),
        )
        return report

    def assess(self, report: DataQualityReport) -> dict[str, dict[str, Any]]:
        """Compare a report against the configured thresholds.

        Returns:
            One entry per check, each with its score, threshold and PASS/FAIL.
        """
        checks = {
            "validity": (report.quality_score, self.validity_min, "min"),
            "completeness": (report.mean_completeness, self.completeness_min, "min"),
            "uniqueness": (
                report.duplicates.duplicate_percentage,
                self.duplicate_max,
                "max",
            ),
        }
        results: dict[str, dict[str, Any]] = {}
        for name, (score, threshold, direction) in checks.items():
            passed = score >= threshold if direction == "min" else score <= threshold
            results[name] = {
                "score": score,
                "threshold": threshold,
                "direction": direction,
                "status": "PASS" if passed else "FAIL",
            }

        passed_count = sum(1 for check in results.values() if check["status"] == "PASS")
        results["overall"] = {
            "checks_passed": passed_count,
            "checks_total": len(checks),
            "status": "PASS" if passed_count == len(checks) else "FAIL",
        }
        return results
