import csv
import io

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services.members_service import xlsx_as_csv


def _workbook_bytes(*, rows: int = 1) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["email", "full_name", "phone"])
    for index in range(rows):
        sheet.append([f"member{index}@example.com", f"Member {index}", f"+1555000{index:04d}"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_xlsx_import_reads_first_sheet_as_csv_rows():
    rows = list(csv.reader(io.StringIO(xlsx_as_csv(_workbook_bytes()).decode("utf-8"))))

    assert rows == [
        ["email", "full_name", "phone"],
        ["member0@example.com", "Member 0", "+15550000000"],
    ]


def test_xlsx_import_rejects_invalid_workbook():
    with pytest.raises(HTTPException) as error:
        xlsx_as_csv(b"not an Excel workbook")

    assert error.value.status_code == 422


def test_xlsx_import_rejects_more_than_ten_thousand_rows():
    with pytest.raises(HTTPException) as error:
        xlsx_as_csv(_workbook_bytes(rows=10_001))

    assert error.value.status_code == 413
