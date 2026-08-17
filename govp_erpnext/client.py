import json
import urllib.error
import urllib.parse
import urllib.request

from govp_erpnext.core import validate_exchange_url


class GovpExchangeError(Exception):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class GovpExchangeClient:
    def __init__(self, base_url, token, timeout=15):
        self.base_url = validate_exchange_url(base_url)
        self.token = token
        self.timeout = timeout

    def request(self, path, method="GET", payload=None, idempotency_key=None):
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "GOVP-for-ERPNext/0.1.4",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=None if payload is None else json.dumps(payload, separators=(",", ":")).encode(),
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:400]
            raise GovpExchangeError(f"GOVP Exchange HTTP {error.code}: {detail}", retryable=error.code in {408, 425, 429} or error.code >= 500) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise GovpExchangeError(f"GOVP Exchange no disponible: {error}", retryable=True) from error

    def inspect(self):
        return self.request("/connectors/me")

    def issue(self, payload, idempotency_key):
        return self.request("/connectors/issue", "POST", payload, idempotency_key)

    def verify(self, code):
        return self.request(f"/govps/{urllib.parse.quote(str(code), safe='')}")
