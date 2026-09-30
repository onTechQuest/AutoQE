from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import Locator, Page

from autoqe.contracts.project_profile import NetworkScope, ProjectProfile

RWA_REVISION = "9dfcb9869533ce8a8963c556facc0d80457f9d39"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class RwaTestActors:
    sender_id: str
    sender_username: str
    sender_first_name: str
    sender_last_name: str
    recipient_id: str
    recipient_username: str
    recipient_first_name: str
    recipient_last_name: str


class RwaProjectAdapter:
    _API_PATHS = {
        "root": "/",
        "seed": "/testData/seed",
        "users": "/testData/users",
        "login": "/login",
        "logout": "/logout",
        "transactions": "/transactions",
    }

    def __init__(
        self,
        rwa_root: str | Path = r"C:\Projects\autoqe-reference-rwa",
        timeout_seconds: float = 8.0,
        http_client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self.rwa_root = Path(rwa_root).resolve()
        self.timeout_seconds = timeout_seconds
        self._http_client_factory = http_client_factory
        self._actors: RwaTestActors | None = None

    @staticmethod
    def _loopback_base_url(value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS or parsed.port is None:
            raise ValueError("RWA execution requires HTTP URLs on localhost, 127.0.0.1, or ::1")
        host = parsed.hostname
        return f"http://{host}:{parsed.port}"

    def _urls(self, project_profile: ProjectProfile) -> tuple[str, str]:
        if project_profile.project_id != "cypress-rwa":
            raise ValueError("RwaProjectAdapter only supports the cypress-rwa ProjectProfile")
        if project_profile.environment.network_scope != NetworkScope.LOCAL_ONLY:
            raise ValueError("RWA reference execution requires LOCAL_ONLY network scope")
        target = project_profile.reference_target
        if target is None or target.revision != RWA_REVISION:
            raise ValueError("RWA ProjectProfile must pin the M1-qualified reference revision")
        if project_profile.environment.reset_adapter != "rwa.yarn_db_seed_dev":
            raise ValueError("RWA ProjectProfile does not declare the qualified deterministic reset")
        if project_profile.application.ui_base_url is None or project_profile.application.api_base_url is None:
            raise ValueError("RWA UI and API base URLs are required")
        return (
            self._loopback_base_url(str(project_profile.application.ui_base_url)),
            self._loopback_base_url(str(project_profile.application.api_base_url)),
        )

    def verify_reference_checkout(self, project_profile: ProjectProfile) -> Mapping[str, str]:
        self._urls(project_profile)
        revision = subprocess.run(
            ["git", "-C", str(self.rwa_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if revision != RWA_REVISION:
            raise ValueError("RWA checkout revision does not match the M1-qualified commit")
        status = subprocess.run(
            ["git", "-C", str(self.rwa_root), "diff", "--name-only", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        changed_paths = {line.strip().replace("\\", "/") for line in status.splitlines() if line.strip()}
        unexpected = changed_paths - {"data/database.json"}
        if unexpected:
            raise ValueError("RWA tracked worktree has unexpected source modifications")
        return {
            "reference_revision": revision,
            "tracked_worktree": "clean" if not changed_paths else "runtime_database_only",
        }

    def verify_ready(self, project_profile: ProjectProfile) -> Mapping[str, str]:
        ui_base, api_base = self._urls(project_profile)
        with self._http_client_factory(timeout=self.timeout_seconds, trust_env=False) as client:
            ui_response = client.get(f"{ui_base}/")
            api_response = client.get(f"{api_base}/")
        if ui_response.status_code != 200 or api_response.status_code != 200:
            raise RuntimeError("RWA frontend or API readiness check failed")
        return {
            "ui_status": str(ui_response.status_code),
            "api_status": str(api_response.status_code),
            "network_scope": "LOCAL_ONLY",
        }

    def reset_environment(self, project_profile: ProjectProfile) -> Mapping[str, str]:
        _, api_base = self._urls(project_profile)
        with self._http_client_factory(timeout=self.timeout_seconds, trust_env=False) as client:
            response = client.post(f"{api_base}/testData/seed")
        if response.status_code != 200:
            raise RuntimeError("RWA deterministic test-data reset failed")
        reset_identity = project_profile.environment.reset_identity or "UNKNOWN"
        if reset_identity.startswith("sha256:"):
            database_path = self.rwa_root / "data" / "database.json"
            seed_path = self.rwa_root / "data" / "database-seed.json"
            seed_bytes = seed_path.read_bytes()
            seed_fingerprint = hashlib.sha256(seed_bytes).hexdigest()
            expected_fingerprint = reset_identity.removeprefix("sha256:").lower()
            if seed_fingerprint != expected_fingerprint:
                raise RuntimeError("RWA database-seed.json does not match the qualified seed fingerprint")
            if json.loads(database_path.read_text(encoding="utf-8")) != json.loads(seed_bytes):
                raise RuntimeError("RWA test-data reset did not restore the qualified seed state")
        self._actors = None
        return {
            "reset_adapter": "rwa.testData.seed",
            "reset_identity": reset_identity,
        }

    def setup_test_data(
        self,
        project_profile: ProjectProfile,
        data_requirements: tuple[str, ...],
    ) -> Mapping[str, str]:
        _, api_base = self._urls(project_profile)
        with self._http_client_factory(timeout=self.timeout_seconds, trust_env=False) as client:
            response = client.get(f"{api_base}/testData/users")
        response.raise_for_status()
        users = response.json().get("results")
        if not isinstance(users, list) or len(users) < 2:
            raise RuntimeError("RWA deterministic user fixtures are unavailable")
        sender, recipient = users[0], users[1]
        required_fields = ("id", "username", "firstName", "lastName")
        if any(not all(isinstance(user.get(field), str) and user[field] for field in required_fields) for user in (sender, recipient)):
            raise RuntimeError("RWA deterministic user fixture is incomplete")
        self._actors = RwaTestActors(
            sender_id=sender["id"],
            sender_username=sender["username"],
            sender_first_name=sender["firstName"],
            sender_last_name=sender["lastName"],
            recipient_id=recipient["id"],
            recipient_username=recipient["username"],
            recipient_first_name=recipient["firstName"],
            recipient_last_name=recipient["lastName"],
        )
        history_fixture_requested = any(
            requirement == "rwa.history.baseline" for requirement in data_requirements
        )
        if history_fixture_requested:
            password = self.test_password()
            with self._http_client_factory(timeout=self.timeout_seconds, trust_env=False) as client:
                login = client.post(
                    f"{api_base}/login",
                    json={"username": self._actors.sender_username, "password": password},
                )
                if login.status_code != 200:
                    raise RuntimeError("RWA history fixture authentication failed")
                created = client.post(
                    f"{api_base}/transactions",
                    json={
                        "transactionType": "payment",
                        "receiverId": self._actors.recipient_id,
                        "amount": 15,
                        "description": "AutoQE M3 history fixture",
                    },
                )
                if created.status_code != 200:
                    raise RuntimeError("RWA history fixture setup failed")
        return {
            "fixture_source": "rwa.testData.users",
            "actor_count": "2",
            "history_fixture_created": str(history_fixture_requested).lower(),
        }

    def authenticate_if_needed(self, project_profile: ProjectProfile) -> Mapping[str, str]:
        self._urls(project_profile)
        password = os.environ.get("RWA_TEST_PASSWORD")
        if not password:
            raise ValueError("RWA_TEST_PASSWORD environment variable is required; its value is never recorded")
        return {"authentication_strategy": "TEST_FIXTURE", "credential_source": "RWA_TEST_PASSWORD"}

    @property
    def actors(self) -> RwaTestActors:
        if self._actors is None:
            raise RuntimeError("RWA test actors are unavailable; call setup_test_data first")
        return self._actors

    @staticmethod
    def test_password() -> str:
        password = os.environ.get("RWA_TEST_PASSWORD")
        if not password:
            raise ValueError("RWA_TEST_PASSWORD environment variable is required")
        return password

    def base_urls(self, project_profile: ProjectProfile) -> tuple[str, str]:
        return self._urls(project_profile)

    def api_endpoint(self, project_profile: ProjectProfile, endpoint: str) -> str:
        _, api_base = self._urls(project_profile)
        path = self._API_PATHS.get(endpoint)
        if path is None:
            raise ValueError(f"unsupported RWA API operation: {endpoint}")
        return f"{api_base}{path}"

    def ui_locator(self, page: Page, name: str, *, actor_role: str | None = None) -> Locator:
        actors = self.actors
        if name == "signin_username":
            return page.get_by_label("Username", exact=True)
        if name == "signin_password":
            return page.get_by_label("Password", exact=True)
        if name == "signin_submit":
            return page.get_by_role("button", name="Sign In", exact=True)
        if name == "new_transaction":
            return page.locator('[data-test="nav-top-new-transaction"]')
        if name == "recipient":
            full_name = f"{actors.recipient_first_name} {actors.recipient_last_name}"
            return page.locator('[data-test^="user-list-item-"]').filter(has_text=full_name).first
        if name == "amount":
            return page.get_by_placeholder("Amount", exact=True)
        if name == "description":
            return page.get_by_placeholder("Add a note", exact=True)
        if name == "submit_payment":
            return page.get_by_role("button", name="Pay", exact=True)
        if name == "payment_confirmation":
            return page.get_by_text("Transaction Submitted!", exact=True)
        if name == "return_to_transactions":
            return page.locator('[data-test="new-transaction-return-to-transactions"]')
        if name == "personal_tab":
            return page.get_by_role("tab", name="Mine", exact=True)
        if name == "transaction_list":
            return page.locator('[data-test="transaction-list"]')
        if name == "transaction_description":
            if not actor_role:
                raise ValueError("actor_role is required for transaction description lookup")
            description = (
                "AutoQE M3 history fixture"
                if actor_role in {"sender", "recipient"}
                else self._unsupported_actor(actor_role)
            )
            return page.get_by_text(description, exact=True)
        if name == "signout":
            return page.locator('[data-test="sidenav-signout"]')
        raise ValueError(f"unsupported RWA UI locator: {name}")

    @staticmethod
    def _unsupported_actor(actor_role: str) -> str:
        raise ValueError(f"unsupported RWA actor role: {actor_role}")