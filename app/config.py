from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-to-a-random-string"
    admin_password: str = "change-me"

    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    admin_email: str = "admin@example.com"
    from_email: str = "noreply@example.com"

    authelia_users_file: str = "/data/users_database.yml"

    app_url: str = "http://localhost:8085"

    token_expiry_hours: int = 48

    default_groups: str = "users"

    database_url: str = "sqlite+aiosqlite:////data/registrations.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def groups_list(self) -> list[str]:
        return [g.strip() for g in self.default_groups.split(",") if g.strip()]


settings = Settings()
