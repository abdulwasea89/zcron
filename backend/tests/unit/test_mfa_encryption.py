from app.core.config import settings
from app.core.mfa_encryption import decrypt_mfa_secret, encrypt_mfa_secret
from app.db.session import _upgrade_sqlite_mfa_secrets
from sqlalchemy import create_engine, text


def test_mfa_secret_is_encrypted_at_rest(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mfa_encryption_key", "")
    encrypted = encrypt_mfa_secret("JBSWY3DPEHPK3PXP")
    assert encrypted.startswith("enc:v1:")
    assert "JBSWY3DPEHPK3PXP" not in encrypted
    assert decrypt_mfa_secret(encrypted) == "JBSWY3DPEHPK3PXP"


def test_local_sqlite_upgrade_encrypts_existing_secret(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "mfa_encryption_key", "")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY, mfa_secret TEXT)"))
        connection.execute(
            text("INSERT INTO users VALUES ('user-1', 'JBSWY3DPEHPK3PXP')")
        )
        _upgrade_sqlite_mfa_secrets(connection)
        stored = connection.execute(
            text("SELECT mfa_secret FROM users WHERE id = 'user-1'")
        ).scalar_one()
    assert stored.startswith("enc:v1:")
    assert decrypt_mfa_secret(stored) == "JBSWY3DPEHPK3PXP"
    engine.dispose()
