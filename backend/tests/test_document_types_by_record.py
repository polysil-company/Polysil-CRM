"""FS-070 (BE-025): every document type belongs on some record, and `other` on all."""

from __future__ import annotations

from api.schemas.documents import DOC_TYPE_LABELS, DOC_TYPES_BY_RECORD, RecordType
from api.services.documents import types


def test_every_type_belongs_somewhere_and_other_everywhere() -> None:
    assert set(DOC_TYPES_BY_RECORD) == set(RecordType.__args__)
    assert set().union(*DOC_TYPES_BY_RECORD.values()) == set(DOC_TYPE_LABELS)
    assert all("other" in kinds for kinds in DOC_TYPES_BY_RECORD.values())


def test_the_filter_keeps_the_label_order_and_no_filter_keeps_everything() -> None:
    assert [t.code for t in types()] == list(DOC_TYPE_LABELS)
    lead = [t.code for t in types("lead")]
    assert lead == [k for k in DOC_TYPE_LABELS if k in DOC_TYPES_BY_RECORD["lead"]]
    assert "gst_certificate" not in lead
