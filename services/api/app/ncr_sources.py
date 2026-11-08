"""Bounded parser for the NCR's public registered debt-counsellor directory."""
from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NCR_REGISTER = "https://www.ncr.org.za/register_of_registrants/registered_dc.php"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def parse_registered_counsellors(document: str, page_url: str) -> list[dict[str, str]]:
    parser = _Text()
    parser.feed(document)
    text = " ".join(parser.parts)
    pattern = re.compile(
        r"Full Name\s*:\s*(.*?)\s+Trading Name\s*:\s*(.*?)\s+"
        r"Phone\s*:\s*(.*?)\s+Fax\s*:\s*(.*?)\s+Email Address\s*:\s*(.*?)\s+"
        r"Final Registration Date\s*:\s*(.*?)\s+NCR Registration No\.?\s*:?\s*(.*?)\s+"
        r"Physical Address\s*:\s*(.*?)\s+Postal Address\s*:\s*(.*?)\s+"
        r"Town\s*:\s*(.*?)\s+Registered!",
        re.IGNORECASE,
    )
    rows = []
    seen = set()
    for match in pattern.finditer(text):
        full_name, trading_name, _, _, _, registration_date, number, address, _, town = (
            " ".join(value.split()) for value in match.groups()
        )
        number = number.upper().replace(" ", "")
        if not re.fullmatch(r"NCRDC\d{1,8}", number) or number in seen:
            continue
        if not full_name or len(full_name) > 180 or len(trading_name) > 180:
            continue
        seen.add(number)
        rows.append({
            "full_name": full_name,
            "trading_name": trading_name,
            "registration_number": number,
            "registration_date": registration_date[:40],
            "physical_address": address[:300],
            "town": town[:120],
            "source_url": page_url,
            "status": "registered",
        })
    return rows


def fetch_registered_counsellors(keyword: str, page: int = 1, limit: int = 100) -> list[dict[str, str]]:
    params = {"page": page}
    if keyword:
        params["keyword"] = keyword
    url = f"{NCR_REGISTER}?{urlencode(params)}"
    request = Request(url, headers={
        "Accept": "text/html",
        "User-Agent": "Arletion/0.3 (public NCR debt counsellor register lookup)",
    })
    with urlopen(request, timeout=15) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("NCR register response exceeded the 4 MB limit.")
    rows = parse_registered_counsellors(raw.decode("utf-8", "replace"), url)
    return rows[:limit]
