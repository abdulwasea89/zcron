from app.services.members_service import _import_header_map


def test_member_import_accepts_common_export_headers_and_prefers_canonical():
    assert _import_header_map(["Email Address", "Member Name", "Mobile Number"]) == {
        "email": "Email Address",
        "full_name": "Member Name",
        "phone": "Mobile Number",
    }
    assert _import_header_map(["Email", "E-mail", "Full Name", "Name", "Phone"]) == {
        "email": "Email",
        "full_name": "Full Name",
        "phone": "Phone",
    }
