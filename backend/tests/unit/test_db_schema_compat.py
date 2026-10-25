from sqlalchemy import create_engine, inspect

from app.db.session import _upgrade_sqlite_late_migration_columns


def test_sqlite_late_migration_upgrade_is_additive_and_repeatable():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE organization_members (id VARCHAR PRIMARY KEY)")
            _upgrade_sqlite_late_migration_columns(connection)
            first_columns = {column["name"] for column in inspect(connection).get_columns("organization_members")}
            _upgrade_sqlite_late_migration_columns(connection)
            second_columns = {column["name"] for column in inspect(connection).get_columns("organization_members")}

        expected = {
            "marketing_email_consent", "marketing_email_consent_at",
            "marketing_sms_consent", "marketing_sms_consent_at",
            "marketing_in_app_consent", "marketing_in_app_consent_at",
            "dashboard_hidden_attention",
        }
        assert expected <= first_columns
        assert second_columns == first_columns
    finally:
        engine.dispose()
