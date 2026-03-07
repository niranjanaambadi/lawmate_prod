from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple, List

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.services.captcha_solver_service import captcha_solver_service

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


class RateLimitError(Exception):
    pass


CASE_TYPE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "WPC": ("WP(C)",),
    "WPCRL": ("WP(Crl)",),
    "CRLA": ("CRL.A", "Crl.A (DB)"),
    "CRLMC": ("CRL.MC",),
    "CRLRC": ("CRL.RC",),
    "CRLRP": ("CRL.RP", "CRL.REV.P"),
    "WA": ("W.A",),
    "FAO": ("FAO",),
    "MFA": ("MFA",),
    "OP": ("OP",),
    "OPCAT": ("OP(CAT)",),
    "RSA": ("RSA",),
    "SA": ("SA",),
    "TA": ("TA",),
    "TESTP": ("Test.P",),
    "TRP": ("TR.P",),
    # Matrimonial / Family
    "MATAPPEAL": ("Mat.A", "MAT.A", "Mat. Appeal", "MAT. APPEAL", "Mat.Appeal"),
    "MATA": ("Mat.A", "MAT.A", "Mat. Appeal"),
    "MATCASE": ("Mat.C", "MAT.C", "Mat. Case"),
    # Criminal misc / revision
    "CRLREV": ("CRL.REV.P", "Crl.Rev.P"),
    "CRLOP": ("CRL.OP", "Crl.OP"),
    # Other appeals
    "CA": ("C.A", "Civil Appeal"),
    "COMA": ("COM.A", "Com.A", "Company Appeal"),
    "ITA": ("IT.A", "ITA", "Income Tax Appeal"),
    "CUST": ("Cust.A", "Customs Appeal"),
    "CEMA": ("CEM.A", "Central Excise Misc Appeal"),
    "COC": ("Cont.C", "Contempt of Court"),
    "CONTP": ("Cont.P", "Contempt Petition"),
}

# Fallback when the dropdown options cannot be parsed from the portal response.
# Keys must be normalized with _normalize_token().
KNOWN_CASE_TYPE_VALUES: Dict[str, str] = {
    "WPC": "157",           # WP(C)
    "WPCRL": "158",         # WP(Crl.)
    "WA": "154",            # WA
    "CRLA": "33",           # CRL.A
    "CRLMC": "37",          # Crl.MC
    "OPC": "99",            # OP(C)
    "OPCRL": "101",         # OP(Crl.)
    "RFA": "122",           # RFA
    "RSA": "130",           # RSA
    "SA": "132",            # SA
    "MFA": "87",            # MFA
    # Matrimonial
    "MATAPPEAL": "80",      # Mat.Appeal
    "MATA": "80",           # Mat.Appeal (alias)
    "MATCAS": "81",         # Mat.Cas
    # Criminal
    "CRLREVPET": "55",      # Crl.Rev.Pet
    "CRLREF": "46",         # CRL.REF
    # Other common
    "FA": "72",             # FA
    "FAO": "74",            # FAO
    "MACA": "83",           # MACA
    "ITA": "110",           # ITA
}

SELECTORS: Dict[str, str] = {
    "case_type": "#case_type",
    "case_no": "#case_no",
    "case_year": "#case_year",
    "captcha_input": "#captcha_typed_login",
    "captcha_hidden": "#captcha_word_login",
    "captcha_image": "#captcha_image img, img[src*='captcha_images'], img[src*='securimage']",
}


class CourtApiService:
    """Playwright-based Kerala HC fetch layer.

    Keeps external source access isolated so future MoU API swap only touches this file.
    """

    def __init__(self) -> None:
        self.status_url = (settings.COURT_PLAYWRIGHT_STATUS_URL or "").strip()
        self.search_url = (settings.COURT_PLAYWRIGHT_SEARCH_URL or "").strip()
        self.view_url = (settings.COURT_PLAYWRIGHT_VIEW_URL or "").strip()
        self.delay_seconds = max(0.0, float(settings.CASE_SYNC_REQUEST_DELAY_SECONDS or 3.0))
        self.headless = bool(settings.PLAYWRIGHT_HEADLESS)
        self.playwright_executable_path = (settings.PLAYWRIGHT_EXECUTABLE_PATH or "").strip() or None
        self.playwright_launch_args = [
            arg.strip()
            for arg in str(settings.PLAYWRIGHT_LAUNCH_ARGS or "").split(",")
            if arg.strip()
        ]
        self._last_call_at = 0.0

    def _launch_browser(self, p: Any) -> Any:
        launch_kwargs: Dict[str, Any] = {"headless": self.headless}

        if self.playwright_executable_path:
            if not os.path.exists(self.playwright_executable_path):
                raise RuntimeError(
                    "PLAYWRIGHT_EXECUTABLE_PATH is set but does not exist: "
                    f"{self.playwright_executable_path}"
                )
            launch_kwargs["executable_path"] = self.playwright_executable_path

        if self.playwright_launch_args:
            launch_kwargs["args"] = self.playwright_launch_args

        try:
            return p.chromium.launch(**launch_kwargs)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message:
                raise RuntimeError(
                    "Chromium executable for Playwright is missing in this runtime. "
                    "Install browser binaries during deploy with `playwright install chromium`, "
                    "or set PLAYWRIGHT_EXECUTABLE_PATH to an existing Chromium binary path."
                ) from exc
            raise

    def _throttle(self) -> None:
        if self.delay_seconds <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_call_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def _normalize_token(self, value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

    def _parse_case_number(self, raw: str) -> Tuple[str, str, str]:
        value = (raw or "").strip().upper()
        # Normalize common noisy suffixes from portal formatting, e.g. "(U)".
        value = re.sub(r"\([^)]*\)\s*$", "", value).strip()
        value = re.sub(r"\s+", " ", value)

        m = re.match(r"^\s*([A-Z][A-Z().\s-]*)\s+(\d+)\s*/\s*(\d{4})\s*$", value)
        if m:
            case_type = re.sub(r"\s+", " ", m.group(1)).strip()
            return case_type, m.group(2).strip(), m.group(3).strip()

        # Accept pure slash format: WP(C)/1570/2026
        m2 = re.match(r"^\s*([A-Z][A-Z().\s-]*)\s*/\s*(\d+)\s*/\s*(\d{4})\s*$", value)
        if m2:
            case_type = re.sub(r"\s+", " ", m2.group(1)).strip()
            return case_type, m2.group(2).strip(), m2.group(3).strip()

        # Accept compact no-space format: WP(C)1570/2026
        m3 = re.match(r"^\s*([A-Z][A-Z().-]*?)\s*(\d+)\s*/\s*(\d{4})\s*$", value)
        if m3:
            case_type = re.sub(r"\s+", " ", m3.group(1)).strip()
            return case_type, m3.group(2).strip(), m3.group(3).strip()

        parts = [p.strip() for p in value.split("/") if p.strip()]
        if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
            case_year = parts[-1]
            case_no = parts[-2]
            case_type = "/".join(parts[:-2]).strip()
            return case_type, case_no, case_year

        raise ValueError(
            "Invalid case number format. Use TYPE + NUMBER + YEAR, e.g. WP(C) 1570/2026 or WP(C)/1570/2026"
        )

    def _case_type_value(self, select_html: str, requested_type: str) -> Optional[str]:
        options = re.findall(r'<option\s+value="([^"]*)"[^>]*>(.*?)</option>', select_html, flags=re.IGNORECASE | re.DOTALL)
        mapping: Dict[str, str] = {}
        for value, label in options:
            key = self._normalize_token(re.sub(r"\s+", " ", label).strip())
            if value and key and key not in mapping:
                mapping[key] = value

        requested_key = self._normalize_token(requested_type)
        if requested_key in mapping:
            return mapping[requested_key]

        for alias in CASE_TYPE_ALIASES.get(requested_key, (requested_type,)):
            alias_key = self._normalize_token(alias)
            if alias_key in mapping:
                return mapping[alias_key]

        for key, value in mapping.items():
            if requested_key in key or key in requested_key:
                return value

        # Hard fallback for known stable Kerala HC case-type ids.
        direct = KNOWN_CASE_TYPE_VALUES.get(requested_key)
        if direct:
            return direct
        for alias in CASE_TYPE_ALIASES.get(requested_key, ()):
            alias_key = self._normalize_token(alias)
            if alias_key in KNOWN_CASE_TYPE_VALUES:
                return KNOWN_CASE_TYPE_VALUES[alias_key]
        return None

    def _extract_click_target(self, html: str) -> Optional[Tuple[str, str]]:
        m = re.search(r"ViewCaseStatus\(\s*'([^']+)'\s*,\s*'([^']+)'", html or "", flags=re.IGNORECASE)
        if not m:
            return None
        return m.group(1).strip(), m.group(2).strip()

    def _new_request_context(self, p: Any, referer: Optional[str] = None) -> Any:
        # Do NOT include X-Requested-With here — it belongs only on AJAX POSTs,
        # not on the initial status-page GET.  CodeIgniter treats AJAX vs normal
        # requests differently, and sending the AJAX header on a page-load GET
        # prevents the server from creating a ci_session cookie.
        headers: Dict[str, str] = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
        if referer:
            headers["Referer"] = referer
        return p.request.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            extra_http_headers=headers,
        )

    def _fetch_status_page_content(self, req: Any, max_retries: int = 3) -> str:
        """
        GET the status page via the request context so that CodeIgniter sets
        ci_session in `req`.  That same `req` must be reused for the search POST
        so the session cookie is carried over.  Retries on transient 5xx.
        """
        last_status = 0
        for attempt in range(max_retries):
            response = req.get(self.status_url, timeout=120000)
            last_status = response.status
            if response.status < 400:
                return response.text()
            if attempt < max_retries - 1:
                time.sleep(2)
        raise RuntimeError(f"Status page returned {last_status} after {max_retries} attempts")

    def _fallback_fetch_status_page_content(self, p: Any) -> str:
        browser = self._launch_browser(p)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
                )
            )
            # Use domcontentloaded so the full HTML (including the case_type select) is parsed.
            page.goto(self.status_url, wait_until="domcontentloaded", timeout=120000)
            return page.content()
        finally:
            browser.close()

    def _read_hidden_captcha(self, page: Any) -> str:
        try:
            el = page.query_selector(SELECTORS["captcha_hidden"])
            if not el:
                return ""
            value = (el.get_attribute("value") or "").strip()
            return value
        except Exception:
            return ""

    def _captcha_image_bytes(self, page: Any) -> Optional[bytes]:
        try:
            el = page.query_selector(SELECTORS["captcha_image"])
            if not el:
                return None
            src = (el.get_attribute("src") or "").strip()
            if not src:
                return None
            if src.startswith("//"):
                src = f"https:{src}"
            elif src.startswith("/"):
                src = f"https://hckinfo.keralacourts.in{src}"
            elif not src.lower().startswith("http"):
                src = f"https://hckinfo.keralacourts.in/digicourt/{src.lstrip('./')}"

            response = page.request.get(src, timeout=30000)
            if response.status >= 400:
                return None
            return response.body()
        except Exception:
            return None

    def _resolve_captcha_text(self, page: Any, prefer_solver: bool = False) -> str:
        hidden = self._read_hidden_captcha(page)
        if hidden and not prefer_solver:
            logger.info("Captcha token source: hidden input")
            return hidden

        if settings.CAPTCHA_ENABLED:
            image_bytes = self._captcha_image_bytes(page)
            solved = captcha_solver_service.solve(image_bytes or b"")
            if solved:
                logger.info("Captcha token source: solver")
                return solved

        return hidden

    def _search_and_fetch_detail(
        self,
        req: Any,
        case_number: str,
        case_type_value: str,
        case_no: str,
        case_year: str,
        captcha_word: str,
    ) -> Optional[Dict[str, Any]]:
        payload = {
            "case_type": case_type_value,
            "case_no": case_no,
            "case_year": case_year,
            "captcha_typed_login": captcha_word,
        }
        search_response = req.post(self.search_url, form=payload, timeout=120000)
        if search_response.status == 429:
            raise RateLimitError("Court portal rate limit reached")
        if search_response.status >= 500:
            raise RuntimeError(f"Court portal returned {search_response.status}")
        if search_response.status >= 400:
            raise RuntimeError(
                "Court search failed with "
                f"{search_response.status} (case_type={case_type_value}, case_no={case_no}, case_year={case_year})"
            )

        search_text = search_response.text()
        try:
            search_json = json.loads(search_text)
        except ValueError:
            search_json = {"p_table": search_text}

        p_table = str(search_json.get("p_table") or "")
        target = self._extract_click_target(p_table)
        if not target:
            low = p_table.lower()
            if "no case" in low or "no record" in low or "not found" in low:
                return None
            return {
                "case_number": case_number,
                "source": self.status_url,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "payload": {"search_json": search_json, "detail_html": p_table},
            }

        cino, case_no_internal = target
        detail_response = req.post(self.view_url, form={"cino": cino, "case_no": case_no_internal}, timeout=120000)
        if detail_response.status >= 400:
            raise RuntimeError(f"Viewcasestatus failed with {detail_response.status}")

        detail_html = detail_response.text()
        proceedings_html = self._fetch_proceedings_html(req, cino=cino, case_no=case_no_internal, detail_html=detail_html)
        return {
            "case_number": case_number,
            "source": self.status_url,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "payload": {
                "search_json": search_json,
                "cino": cino,
                "case_no": case_no_internal,
                "detail_html": detail_html,
                "proceedings_html": proceedings_html,
            },
        }

    def _search_and_fetch_detail_via_browser(
        self,
        p: Any,
        case_number: str,
        case_no: str,
        case_year: str,
        case_type: str = "",
        case_type_value: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Playwright headless-browser fallback.

        Pass either ``case_type_value`` (already resolved) **or** ``case_type``
        (raw string such as "Mat.Appeal") and this method will extract the
        dropdown value from the loaded page content.
        """
        browser = self._launch_browser(p)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            # Navigate to the status page to establish the ci_session cookie.
            # CodeIgniter requires the same session from GET → POST.
            # Retry up to 3 times if the portal returns a transient 5xx error.
            for attempt in range(3):
                nav_resp = page.goto(self.status_url, wait_until="domcontentloaded", timeout=120000)
                if nav_resp and nav_resp.status < 400:
                    break
                if attempt < 2:
                    time.sleep(2)
            else:
                raise RuntimeError(
                    f"Court portal status page returned {nav_resp.status if nav_resp else 'no response'} "
                    "after 3 attempts — ci_session could not be established."
                )

            # If case_type_value was not pre-resolved, extract it from the
            # page content now (avoids an extra browser launch just to get the dropdown).
            if not case_type_value and case_type:
                page_content = page.content()
                select_block = ""
                m_sel = re.search(
                    r"(<select[^>]*id=\"case_type\"[\s\S]*?</select>)",
                    page_content,
                    flags=re.IGNORECASE,
                )
                if m_sel:
                    select_block = m_sel.group(1)
                case_type_value = self._case_type_value(select_block or page_content, case_type)
                if not case_type_value:
                    raise ValueError(f"INVALID_CASE_TYPE: {case_type}")
            if not case_type_value:
                raise ValueError("case_type_value could not be determined for browser fallback")

            # Read captcha token from the hidden input (quick, no interaction needed).
            captcha_word = self._resolve_captcha_text(page, prefer_solver=False)

            response = page.request.post(
                self.search_url,
                form={
                    "case_type": case_type_value,
                    "case_no": case_no,
                    "case_year": case_year,
                    "captcha_typed_login": captcha_word,
                },
                timeout=120000,
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.status_url},
            )
            if response.status == 400 and settings.CAPTCHA_ENABLED:
                # Retry once with OCR/human-solver captcha token (re-establish session).
                nav_resp2 = page.goto(self.status_url, wait_until="domcontentloaded", timeout=120000)
                if nav_resp2 and nav_resp2.status >= 400:
                    raise RuntimeError(f"Court portal unavailable on captcha retry ({nav_resp2.status})")
                captcha_word = self._resolve_captcha_text(page, prefer_solver=True)
                response = page.request.post(
                    self.search_url,
                    form={
                        "case_type": case_type_value,
                        "case_no": case_no,
                        "case_year": case_year,
                        "captcha_typed_login": captcha_word,
                    },
                    timeout=120000,
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.status_url},
                )
            if response.status >= 400:
                raise RuntimeError(
                    "Court search failed with "
                    f"{response.status} (case_type={case_type_value}, case_no={case_no}, case_year={case_year})"
                )

            search_text = response.text()
            try:
                search_json = json.loads(search_text)
            except ValueError:
                search_json = {"p_table": search_text}

            p_table = str(search_json.get("p_table") or "")
            target = self._extract_click_target(p_table)
            if not target:
                low = p_table.lower()
                if "no case" in low or "no record" in low or "not found" in low:
                    return None
                return {
                    "case_number": case_number,
                    "source": self.status_url,
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "payload": {"search_json": search_json, "detail_html": p_table},
                }

            cino, case_no_internal = target
            detail_response = page.request.post(
                self.view_url,
                form={"cino": cino, "case_no": case_no_internal},
                timeout=120000,
            )
            if detail_response.status >= 400:
                raise RuntimeError(f"Viewcasestatus failed with {detail_response.status}")

            detail_html = detail_response.text()
            proceedings_html = self._fetch_proceedings_html(page.request, cino=cino, case_no=case_no_internal, detail_html=detail_html)
            return {
                "case_number": case_number,
                "source": self.status_url,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "payload": {
                    "search_json": search_json,
                    "cino": cino,
                    "case_no": case_no_internal,
                    "detail_html": detail_html,
                    "proceedings_html": proceedings_html,
                },
            }
        finally:
            browser.close()

    def _extract_proceedings_payload_candidates(self, detail_html: str, cino: str, case_no: str) -> List[Dict[str, str]]:
        candidates: List[Dict[str, str]] = []
        html = detail_html or ""

        # The detail page sets a hidden input: <input id="cinoz" name="cinoz" value="CINO">
        # and the JS does:  $.ajax({ data: { cinoz: cinoz } })
        # Extract cinoz value from the hidden input if present.
        cinoz_val = cino  # default to cino
        m_cinoz = re.search(r'id=["\']cinoz["\']\s+name=["\']cinoz["\']\s+value=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not m_cinoz:
            m_cinoz = re.search(r'name=["\']cinoz["\']\s[^>]*value=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not m_cinoz:
            m_cinoz = re.search(r'value=["\']([^"\']+)["\']\s[^>]*name=["\']cinoz["\']', html, re.IGNORECASE)
        if m_cinoz:
            cinoz_val = m_cinoz.group(1).strip()

        # cinoz-keyed payload (current portal AJAX format)
        candidates.append({"cinoz": cinoz_val})

        # Common pattern: getProceedings('cino','case_no') or with more args.
        match = re.search(r"getProceedings\(([^)]*)\)", html, flags=re.IGNORECASE)
        if match:
            arg_blob = match.group(1)
            quoted = re.findall(r"'([^']*)'|\"([^\"]*)\"", arg_blob)
            args = [a or b for (a, b) in quoted if (a or b)]
            if len(args) >= 2:
                a0 = args[0].strip()
                a1 = args[1].strip()
                if a0 and a1:
                    candidates.append({"cino": a0, "case_no": a1})
                    candidates.append({"cino": a0, "caseno": a1})
                    candidates.append({"cino": a0, "case_no_internal": a1})

        candidates.extend(
            [
                {"cino": cino, "case_no": case_no},
                {"cino": cino, "caseno": case_no},
                {"cino": cino, "case_no_internal": case_no},
            ]
        )

        deduped: List[Dict[str, str]] = []
        seen = set()
        for item in candidates:
            key = tuple(sorted(item.items()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _fetch_proceedings_html(self, req_like: Any, cino: str, case_no: str, detail_html: str) -> str:
        """
        Fetch hearing-history table HTML from Queryproceedings/getProceedings.
        Tries a few payload key variants because the portal changes naming across screens.
        """
        endpoint = "https://hckinfo.keralacourts.in/digicourt/index.php/Queryproceedings/getProceedings"
        candidates = self._extract_proceedings_payload_candidates(detail_html, cino=cino, case_no=case_no)
        for form in candidates:
            try:
                res = req_like.post(
                    endpoint,
                    form=form,
                    timeout=120000,
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.status_url},
                )
                if res.status >= 400:
                    continue
                text = res.text() or ""
                if "HISTORY OF CASE HEARING" in text.upper() or ("<table" in text.lower() and "Cause List Type" in text):
                    logger.info("Proceedings fetch success with payload keys: %s", ",".join(sorted(form.keys())))
                    return text
            except Exception:
                continue
        logger.warning("Proceedings fetch failed for cino=%s case_no=%s", cino, case_no)
        return ""

    # ──────────────────────────────────────────────────────────────────────────
    # httpx-based primary scrape path (fixes ci_session 500 errors)
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_case_status_via_httpx(
        self,
        case_number: str,
        case_type: str,
        case_no: str,
        case_year: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Primary scrape path using httpx.Client() — equivalent to requests.Session().

        httpx.Client() maintains a persistent cookie jar, so the CodeIgniter
        ci_session cookie set on the initial GET is automatically carried to
        every subsequent POST.  This is the correct fix for the portal returning
        HTTP 500 when the session is missing.

        Raises ValueError for INVALID_CASE_TYPE (do not retry via browser).
        Raises RuntimeError for network / portal errors (browser fallback allowed).
        """
        base_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        with httpx.Client(headers=base_headers, follow_redirects=True, timeout=60.0) as client:
            # ── Step 1: GET status page — sets ci_session in client.cookies ──
            logger.info("httpx: GET %s", self.status_url)
            status_resp = client.get(self.status_url)
            logger.info(
                "httpx: status page HTTP %s  cookies=%s",
                status_resp.status_code,
                list(client.cookies.keys()),
            )
            if status_resp.status_code >= 400:
                raise RuntimeError(
                    f"httpx: Status page returned {status_resp.status_code}"
                )
            content = status_resp.text

            # ── Step 2: Resolve case_type dropdown value ──
            select_block = ""
            m_select = re.search(
                r"(<select[^>]*id=\"case_type\"[\s\S]*?</select>)",
                content,
                flags=re.IGNORECASE,
            )
            if m_select:
                select_block = m_select.group(1)
            case_type_value = self._case_type_value(select_block or content, case_type)
            if not case_type_value:
                raise ValueError(f"INVALID_CASE_TYPE: {case_type}")

            # ── Step 3: Parse ALL hidden inputs (CSRF token, captcha, etc.) ──
            # CodeIgniter CSRF protection requires the hidden CSRF token to be
            # present in the POST body.  We also pick up captcha_word_login here
            # (if it's rendered server-side rather than by JavaScript).
            hidden_fields: Dict[str, str] = {}
            for m_hidden in re.finditer(
                r"<input[^>]+type=[\"']hidden[\"'][^>]*>",
                content,
                flags=re.IGNORECASE,
            ):
                tag = m_hidden.group(0)
                name_m = re.search(r"\bname=[\"']([^\"']+)[\"']", tag, re.IGNORECASE)
                val_m = re.search(r"\bvalue=[\"']([^\"']*)[\"']", tag, re.IGNORECASE)
                if name_m:
                    hidden_fields[name_m.group(1)] = val_m.group(1) if val_m else ""

            captcha_word = hidden_fields.get("captcha_word_login", "")
            logger.info(
                "httpx: case_type_value=%s  captcha_word_len=%d  hidden_fields=%s",
                case_type_value,
                len(captcha_word),
                list(hidden_fields.keys()),
            )

            # ── Step 4: POST search — ci_session + CSRF carried automatically ──
            post_data: Dict[str, str] = {
                **hidden_fields,           # includes CSRF token + captcha_word_login
                "case_type": case_type_value,
                "case_no": case_no,
                "case_year": case_year,
                "captcha_typed_login": captcha_word,
            }
            search_resp = client.post(
                self.search_url,
                data=post_data,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": self.status_url,
                },
            )
            logger.info("httpx: search POST HTTP %s", search_resp.status_code)
            if search_resp.status_code == 429:
                raise RateLimitError("Court portal rate limit reached")
            if search_resp.status_code >= 400:
                raise RuntimeError(
                    f"Court search failed with {search_resp.status_code} "
                    f"(case_type={case_type_value}, case_no={case_no}, case_year={case_year})"
                )

            search_text = search_resp.text
            try:
                search_json = json.loads(search_text)
            except ValueError:
                search_json = {"p_table": search_text}

            p_table = str(search_json.get("p_table") or "")
            target = self._extract_click_target(p_table)
            if not target:
                low = p_table.lower()
                if "no case" in low or "no record" in low or "not found" in low:
                    return None
                return {
                    "case_number": case_number,
                    "source": self.status_url,
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "payload": {"search_json": search_json, "detail_html": p_table},
                }

            # ── Step 5: POST view detail ──
            cino, case_no_internal = target
            detail_resp = client.post(
                self.view_url,
                data={"cino": cino, "case_no": case_no_internal},
                headers={"Referer": self.search_url},
            )
            if detail_resp.status_code >= 400:
                raise RuntimeError(
                    f"Viewcasestatus failed with {detail_resp.status_code}"
                )
            detail_html = detail_resp.text

            # ── Step 6: Fetch hearing history ──
            proceedings_html = self._fetch_proceedings_html_httpx(
                client,
                cino=cino,
                case_no=case_no_internal,
                detail_html=detail_html,
            )
            return {
                "case_number": case_number,
                "source": self.status_url,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "payload": {
                    "search_json": search_json,
                    "cino": cino,
                    "case_no": case_no_internal,
                    "detail_html": detail_html,
                    "proceedings_html": proceedings_html,
                },
            }

    def _fetch_proceedings_html_httpx(
        self,
        client: httpx.Client,
        cino: str,
        case_no: str,
        detail_html: str,
    ) -> str:
        """
        Fetch hearing-history HTML using an existing httpx.Client session
        (so ci_session is carried automatically).
        """
        endpoint = (
            "https://hckinfo.keralacourts.in/digicourt/index.php"
            "/Queryproceedings/getProceedings"
        )
        candidates = self._extract_proceedings_payload_candidates(
            detail_html, cino=cino, case_no=case_no
        )
        for form in candidates:
            try:
                res = client.post(
                    endpoint,
                    data=form,
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": self.status_url,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                if res.status_code >= 400:
                    continue
                text = res.text or ""
                if "HISTORY OF CASE HEARING" in text.upper() or (
                    "<table" in text.lower() and "Cause List Type" in text
                ):
                    logger.info(
                        "httpx proceedings success with keys: %s",
                        ",".join(sorted(form.keys())),
                    )
                    return text
            except Exception:
                continue
        logger.warning(
            "httpx proceedings fetch failed for cino=%s case_no=%s", cino, case_no
        )
        return ""

    def fetch_case_status(self, case_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch live case status from the Kerala HC portal.

        Strategy (in order):
        1. **httpx.Client()** — behaves like requests.Session(); persistent cookie
           jar carries the CodeIgniter ci_session from GET → POST automatically.
           This is the primary path and fixes the "Court portal returned 500" errors
           that occurred because Playwright's request context discards cookies.
        2. **Playwright headless Chromium** — only reached if httpx fails for a
           non-INVALID_CASE_TYPE reason (e.g., CAPTCHA change, JS-rendered page).
        """
        if not self.status_url or not self.search_url or not self.view_url:
            raise ValueError("Court Playwright URLs are not configured")

        case_type, case_no, case_year = self._parse_case_number(case_number)
        self._throttle()

        try:
            # ── Primary path: httpx.Client with persistent cookie jar ──────────
            try:
                return self._fetch_case_status_via_httpx(
                    case_number, case_type, case_no, case_year
                )
            except ValueError:
                raise  # INVALID_CASE_TYPE — a browser won't help
            except Exception as exc:
                logger.warning(
                    "httpx path failed for %s (%s) — falling back to Playwright browser",
                    case_number,
                    exc,
                )

            # ── Fallback path: Playwright headless Chromium ───────────────────
            if sync_playwright is None:
                raise RuntimeError(
                    "Playwright Python package is not installed. "
                    "Install with `pip install playwright` and install the browser "
                    "with `playwright install chromium`."
                )
            with sync_playwright() as p:
                return self._search_and_fetch_detail_via_browser(
                    p=p,
                    case_number=case_number,
                    case_no=case_no,
                    case_year=case_year,
                    case_type=case_type,  # resolved inside from page dropdown
                )
        finally:
            self._last_call_at = time.monotonic()

court_api_service = CourtApiService()
