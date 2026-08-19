from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server configuration
    environment: str = "development"
    port: int = 8003
    api_v1_str: str = "/api/v1"
    service_name: str = "notification-service"

    # Firestore
    firestore_database: str = "(default)"
    google_cloud_project: str = ""
    google_application_credentials: str = ""

    # Identity Service S2S Authentication
    identity_service_url: str = "http://localhost:8002"
    identity_issuer: str = "http://localhost:8002"
    identity_jwks_url: str = "http://localhost:8002/.well-known/jwks.json"
    identity_audience: str = "notification-service"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"

    # Resend Email Provider
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    default_from_email: str = "noreply@example.com"
    resend_api_base_url: str = "https://api.resend.com"

    # Cloud Tasks
    cloud_tasks_project: str = ""
    cloud_tasks_location: str = "us-central1"
    cloud_tasks_queue: str = "notification-delivery"
    cloud_tasks_worker_url: str = ""
    cloud_tasks_service_account_email: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8002"]

    # Worker Settings
    max_delivery_attempts: int = 5
    enable_mock_delivery: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
