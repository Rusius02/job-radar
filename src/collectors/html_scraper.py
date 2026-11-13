from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request


class ScrapingNotAllowedError(RuntimeError):
    """Raised when a URL cannot be fetched under the configured safeguards."""


class HtmlScraper:
    """Fetch HTML only after explicit terms review and a robots.txt check."""

    _ROBOTS_MAX_BYTES = 512 * 1024

    def __init__(
        self,
        user_agent: str,
        *,
        timeout: float = 10.0,
        max_bytes: int = 2 * 1024 * 1024,
        min_interval: float = 1.0,
    ) -> None:
        if not user_agent.strip() or user_agent.strip() == "*":
            raise ValueError("Provide a descriptive user-agent, not '*'.")
        if timeout <= 0 or max_bytes <= 0 or min_interval < 0:
            raise ValueError("timeout and max_bytes must be positive; min_interval cannot be negative.")

        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.min_interval = min_interval
        self._last_request: dict[str, float] = {}
        self._request_lock = threading.Lock()

    def fetch(self, url: str, *, terms_reviewed: bool = False) -> str:
        """Return a page's HTML, requiring the caller to confirm terms review."""
        if not terms_reviewed:
            raise ScrapingNotAllowedError(
                "Review the site's terms and applicable law, then pass terms_reviewed=True."
            )

        parsed_url = self._validate_url(url)
        if not self._robots_allows(parsed_url, url):
            raise ScrapingNotAllowedError(
                f"robots.txt disallows scraping {_display_url(url)!r}."
            )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with self._open(request) as response:
                status = response.getcode()
                if status is not None and not 200 <= status < 300:
                    raise ScrapingNotAllowedError(f"Unexpected HTTP status {status} for {url!r}.")
                if response.geturl() != url:
                    raise ScrapingNotAllowedError(
                        f"Redirects are not followed; check permissions for the destination URL."
                    )

                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise ScrapingNotAllowedError(
                        f"Expected an HTML response, received {content_type!r}."
                    )

                body = response.read(self.max_bytes + 1)
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise ScrapingNotAllowedError(
                    "Redirects are not followed; check permissions for the destination URL."
                ) from error
            raise ScrapingNotAllowedError(f"HTTP request failed with status {error.code}.") from error
        except urllib.error.URLError as error:
            raise ScrapingNotAllowedError(
                f"Could not fetch {_display_url(url)!r}: {error.reason}"
            ) from error

        if len(body) > self.max_bytes:
            raise ScrapingNotAllowedError(f"HTML response exceeds the {self.max_bytes}-byte limit.")

        charset = response.headers.get_content_charset() or "utf-8"
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")

    @staticmethod
    def _validate_url(url: str) -> urllib.parse.SplitResult:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("URL must use http or https and include a hostname.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs containing credentials are not allowed.")
        return parsed

    def _robots_allows(self, parsed_url: urllib.parse.SplitResult, url: str) -> bool:
        robots_url = urllib.parse.urlunsplit(
            (parsed_url.scheme, parsed_url.netloc, "/robots.txt", "", "")
        )
        request = urllib.request.Request(robots_url, headers={"User-Agent": self.user_agent})
        try:
            with self._open(request) as response:
                body = response.read(self._ROBOTS_MAX_BYTES + 1)
                if len(body) > self._ROBOTS_MAX_BYTES:
                    raise ScrapingNotAllowedError("robots.txt exceeds the size limit.")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return True
            raise ScrapingNotAllowedError(
                f"Could not verify robots.txt (HTTP {error.code}); refusing to scrape."
            ) from error
        except urllib.error.URLError as error:
            raise ScrapingNotAllowedError(
                f"Could not verify robots.txt ({error.reason}); refusing to scrape."
            ) from error

        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(self.user_agent, url)

    def _open(self, request: urllib.request.Request):
        self._wait_for_host(request.full_url)
        opener = urllib.request.build_opener(_NoRedirectHandler)
        return opener.open(request, timeout=self.timeout)

    def _wait_for_host(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).netloc.casefold()
        with self._request_lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last_request.get(host, 0.0))
            if wait > 0:
                time.sleep(wait)
            self._last_request[host] = time.monotonic()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _display_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, "", "")
    )
