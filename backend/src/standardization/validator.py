"""
Validation layer.
Checks ingested records for completeness, type sanity, and obvious anomalies.
"""

from utils import get_logger

logger = get_logger("validator")


class ValidationError(Exception):
    pass


class RecordValidator:
    """Validate normalized records before warehouse ingestion."""

    REQUIRED_FIELDS = [
        "company_id", "financial_item", "financial_category",
        "year", "value", "units", "source_file",
    ]

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.warnings: list = []

    # ----------------------------------------------------------------

    def validate_batch(self, records: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Split records into (valid, rejected).
        Each rejected record carries an added '_reason' key.
        """
        valid, rejected = [], []
        for rec in records:
            try:
                self._validate_one(rec)
                valid.append(rec)
            except ValidationError as e:
                rec_copy = dict(rec)
                rec_copy["_reason"] = str(e)
                rejected.append(rec_copy)
                logger.warning(f"Rejected record: {e}")
        logger.info(f"Validation: {len(valid)} valid, {len(rejected)} rejected")
        return valid, rejected

    # ----------------------------------------------------------------

    def _validate_one(self, rec: dict) -> None:
        for f in self.REQUIRED_FIELDS:
            if rec.get(f) in (None, ""):
                raise ValidationError(f"Missing field '{f}'")

        # Type checks
        try:
            float(rec["value"])
        except (TypeError, ValueError):
            raise ValidationError(f"Non-numeric value for {rec.get('financial_item')}: {rec.get('value')}")

        # Year format check
        yr = str(rec["year"])
        if not (yr.startswith("FY") and yr[2:].isdigit()):
            raise ValidationError(f"Bad year format '{yr}' (expected 'FYxx')")

        # Units check
        allowed_units = {"INR Million", "INR Crs", "%", "Ratio", "Days", "INR"}
        if rec.get("units") not in allowed_units:
            msg = f"Unknown units '{rec.get('units')}' for {rec.get('financial_item')}"
            if self.strict:
                raise ValidationError(msg)
            self.warnings.append(msg)
