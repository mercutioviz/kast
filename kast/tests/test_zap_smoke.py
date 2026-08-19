"""Smoke test for the pinned ZAP image.

Opt-in: set ``KAST_ZAP_SMOKE=1``. It pulls and boots a real container, so it
does not belong in the default suite — but it is the gate to run before
bumping ``ZAP_IMAGE_DIGEST``.

What it pins is the shape of the break that shipped in v3.0.33: ZAP 2.17
routes its API through the proxy rather than serving it on the proxy port
directly, so a version bump can leave every endpoint reachable by curl and
still make every kast scan fail. Asserting "the container starts" would not
have caught that. These assertions go through ``ZAPAPIClient`` — the same
proxied session a scan uses — and touch the specific endpoints the stall
taxonomy and the automation flow depend on.
"""

import os
import subprocess
import time
import uuid

import pytest

from kast.scripts.zap_api_client import _JOB_LIVENESS_PROBES, ZAPAPIClient
from kast.scripts.zap_providers import ZAP_IMAGE, ZAP_TESTED_VERSION

pytestmark = pytest.mark.skipif(
    os.environ.get("KAST_ZAP_SMOKE") != "1",
    reason="ZAP smoke test is opt-in: set KAST_ZAP_SMOKE=1 (pulls and runs a container)",
)

API_KEY = "kast-smoke"
BOOT_TIMEOUT = 180


@pytest.fixture(scope="module")
def zap_container():
    if subprocess.run(["docker", "--version"], capture_output=True).returncode != 0:
        pytest.skip("docker not available")

    name = f"kast-zap-smoke-{uuid.uuid4().hex[:8]}"
    port = 18080
    proc = subprocess.run([
        "docker", "run", "-d", "--name", name, "-p", f"{port}:8080", ZAP_IMAGE,
        "zap.sh", "-daemon", "-port", "8080",
        "-config", f"api.key={API_KEY}",
        "-config", "api.addrs.addr.name=.*",
        "-config", "api.addrs.addr.regex=true",
        "-config", "network.localServers.mainProxy.address=0.0.0.0",
        "-config", "autoupdate.checkOnStart=false",
    ], capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.fail(f"Could not start pinned ZAP image {ZAP_IMAGE}: {proc.stderr}")

    client = ZAPAPIClient(f"http://localhost:{port}", api_key=API_KEY, timeout=10)
    deadline = time.time() + BOOT_TIMEOUT
    while time.time() < deadline:
        try:
            if client._make_request("/JSON/core/view/version/").get("version"):
                break
        except Exception:
            pass
        time.sleep(3)
    else:
        logs = subprocess.run(["docker", "logs", "--tail", "40", name],
                              capture_output=True, text=True).stdout
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        pytest.fail(f"ZAP API never came up within {BOOT_TIMEOUT}s. Logs:\n{logs}")

    yield client

    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def test_pinned_image_reports_tested_version(zap_container):
    """The digest must still be the ZAP release the constants claim."""
    version = zap_container._make_request("/JSON/core/view/version/")["version"]
    assert version == ZAP_TESTED_VERSION, (
        f"Pinned digest runs ZAP {version}, but ZAP_TESTED_VERSION says "
        f"{ZAP_TESTED_VERSION} — update the constants together."
    )


def test_api_reachable_through_the_proxy(zap_container):
    """The API must answer on the path ZAPAPIClient uses.

    ``ZAPAPIClient`` routes every request through ZAP as an HTTP proxy because
    2.14+ stopped serving the API on the proxy port directly. This assertion is
    the one that fails first when that arrangement changes again.
    """
    assert zap_container._make_request("/JSON/core/view/version/").get("version")


def _raw_get(client, endpoint, **params):
    """Hit an endpoint through the proxied session without raise_for_status.

    ZAP answers 400 for a well-formed call in the wrong state — ascan/status
    with no scan running, planProgress with an unknown plan id. That is a
    live endpoint, and only a 404 means the route is gone.
    """
    return client.session.get(f"http://zap{endpoint}", params=params, timeout=client.timeout)


def test_automation_framework_present(zap_container):
    """Every scan runs through an automation plan; the add-on must be loaded."""
    response = _raw_get(zap_container, "/JSON/automation/view/planProgress/", planId="0")
    assert response.status_code != 404, (
        f"automation/view/planProgress/ is gone on ZAP {ZAP_TESTED_VERSION} — "
        "the Automation Framework add-on is missing or the route moved."
    )


def test_liveness_probe_endpoints_are_routed(zap_container):
    """Every probe in the stall taxonomy must still be a real endpoint.

    A probe that 404s reads as "not alive" to ``_probe_percent``, which counts
    a stall and aborts a healthy scan after two poll cycles. A 400 here is
    correct and expected: nothing is scanning yet.
    """
    probes = {job: ep for job, ep in _JOB_LIVENESS_PROBES.items() if ep}
    assert probes, "Taxonomy has no probes — stall detection is fully disabled"
    for job_type, endpoint in probes.items():
        response = _raw_get(zap_container, endpoint)
        assert response.status_code != 404, (
            f"Liveness probe for '{job_type}' ({endpoint}) 404s on ZAP "
            f"{ZAP_TESTED_VERSION} — stall detection would abort healthy scans."
        )
