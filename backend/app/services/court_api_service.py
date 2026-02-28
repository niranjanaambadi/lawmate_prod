from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Tuple, List

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
}

# Fallback when the dropdown options cannot be parsed from the portal response.
# Keys must be normalized with _normalize_token().
KNOWN_CASE_TYPE_VALUES: Dict[str, str] = {
    "WPC": "157",      # WP(C)
    "WPCRL": "158",    # WP(Crl.)
    "WA": "154",       # WA
    "CRLA": "33",      # CRL.A
    "CRLMC": "37",     # Crl.MC
    "OPC": "99",       # OP(C)
    "OPCRL": "101",    # OP(Crl.)
    "RFA": "122",      # RFA
    "RSA": "130",      # RSA
    "SA": "132",       # SA
    "MFA": "87",       # MFA
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
        self._last_call_at = 0.0

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
        headers: Dict[str, str] = {"Accept": "text/html,application/json,*/*;q=0.8"}
        if referer:
            headers["Referer"] = referer
        headers["X-Requested-With"] = "XMLHttpRequest"
        return p.request.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            extra_http_headers=headers,
        )

    def _fetch_status_page_content(self, req: Any) -> str:
        response = req.get(self.status_url, timeout=120000)
        if response.status >= 400:
            raise RuntimeError(f"Status page returned {response.status}")
        return response.text()

    def _fallback_fetch_status_page_content(self, p: Any) -> str:
        browser = p.chromium.launch(headless=self.headless)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
                )
            )
            page.goto(self.status_url, wait_until="commit", timeout=120000)
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
        case_type_value: str,
        case_no: str,
        case_year: str,
    ) -> Optional[Dict[str, Any]]:
        browser = p.chromium.launch(headless=self.headless)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
                )
            )
            page.goto(self.status_url, wait_until="commit", timeout=120000)
            page.select_option(SELECTORS["case_type"], case_type_value)
            page.fill(SELECTORS["case_no"], case_no)
            page.fill(SELECTORS["case_year"], case_year)

            captcha_word = self._resolve_captcha_text(page, prefer_solver=False)
            if captcha_word:
                page.fill(SELECTORS["captcha_input"], captcha_word)

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
                # Retry once with OCR/human-solver token in case hidden value is rejected.
                page.goto(self.status_url, wait_until="commit", timeout=120000)
                page.select_option(SELECTORS["case_type"], case_type_value)
                page.fill(SELECTORS["case_no"], case_no)
                page.fill(SELECTORS["case_year"], case_year)
                captcha_word = self._resolve_captcha_text(page, prefer_solver=True)
                if captcha_word:
                    page.fill(SELECTORS["captcha_input"], captcha_word)
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

    def fetch_case_status(self, case_number: str) -> Optional[Dict[str, Any]]:
        if sync_playwright is None:
            raise RuntimeError("Playwright is not installed. Install with: pip install playwright && playwright install chromium")
        if not self.status_url or not self.search_url or not self.view_url:
            raise ValueError("Court Playwright URLs are not configured")

        case_type, case_no, case_year = self._parse_case_number(case_number)
        self._throttle()

        try:
            with sync_playwright() as p:
                req = self._new_request_context(p, referer=self.status_url)
                try:
                    content = self._fetch_status_page_content(req)
                except Exception as exc:
                    logger.warning("Status page request fetch failed, using browser fallback: %s", str(exc))
                    content = self._fallback_fetch_status_page_content(p)

                select_block = ""
                m_select = re.search(r"(<select[^>]*id=\"case_type\"[\s\S]*?</select>)", content, flags=re.IGNORECASE)
                if m_select:
                    select_block = m_select.group(1)
                case_type_value = self._case_type_value(select_block or content, case_type)
                if not case_type_value:
                    raise ValueError(f"INVALID_CASE_TYPE: {case_type}")

                captcha_word = ""
                m_captcha = re.search(r'id="captcha_word_login"\s+value="([^"]+)"', content, flags=re.IGNORECASE)
                if m_captcha:
                    captcha_word = m_captcha.group(1).strip()

                try:
                    return self._search_and_fetch_detail(
                        req=req,
                        case_number=case_number,
                        case_type_value=case_type_value,
                        case_no=case_no,
                        case_year=case_year,
                        captcha_word=captcha_word,
                    )
                except Exception as exc:
                    if "Court search failed with 400" in str(exc):
                        logger.warning("Court search 400 via request context, retrying in browser context")
                        return self._search_and_fetch_detail_via_browser(
                            p=p,
                            case_number=case_number,
                            case_type_value=case_type_value,
                            case_no=case_no,
                            case_year=case_year,
                        )
                    raise
                finally:
                    req.dispose()
        finally:
            self._last_call_at = time.monotonic()

court_api_service = CourtApiService()
