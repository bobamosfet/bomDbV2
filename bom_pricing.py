#!/usr/bin/env python3
"""
BOM Pricing Engine
Queries DigiKey and Mouser APIs to retrieve current component pricing.
No GUI code — returns structured results for callers to handle.

Requires: pip install requests
"""

import json
import os
import time

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


CONFIG_FILE = 'bom_pricing_config.json'


def load_config():
    """Load API credentials from config file."""
    config = {
        'digikey_client_id': '',
        'digikey_client_secret': '',
        'mouser_api_key': '',
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                saved = json.load(f)
                config.update(saved)
    except Exception:
        pass
    return config


def save_config(config):
    """Save API credentials to config file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


# ============================================================
# DigiKey API Client (OAuth2 + Product Search v4)
# ============================================================

class DigiKeyClient:
    """Client for DigiKey Product Information API v4.

    Authentication uses OAuth2 client credentials flow.
    Ref: https://developer.digikey.com/documentation
    """

    TOKEN_URL = 'https://api.digikey.com/v1/oauth2/token'
    SEARCH_URL = 'https://api.digikey.com/products/v4/search/keyword'

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = None
        self._token_expiry = 0  # epoch timestamp

    def is_configured(self):
        """Return True if credentials are present."""
        return bool(self.client_id and self.client_secret)

    def _ensure_token(self):
        """Obtain or refresh the OAuth2 access token."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return  # Token still valid (with 60s safety margin)

        resp = requests.post(self.TOKEN_URL, data={
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }, timeout=15)

        if resp.status_code != 200:
            raise Exception(
                f"DigiKey OAuth2 token request failed (HTTP {resp.status_code}):\n"
                f"{resp.text[:500]}"
            )

        data = resp.json()
        self._access_token = data['access_token']
        self._token_expiry = time.time() + data.get('expires_in', 3600)

    def search_part(self, mfg_part_number):
        """Search for a part by manufacturer part number.

        Returns dict with keys:
            found (bool), digikey_pn (str), unit_price (float or None),
            description (str), manufacturer (str), error (str or None)
        """
        result = {
            'found': False,
            'digikey_pn': '',
            'unit_price': None,
            'description': '',
            'manufacturer': '',
            'error': None,
        }

        try:
            self._ensure_token()

            headers = {
                'Authorization': f'Bearer {self._access_token}',
                'X-DIGIKEY-Client-Id': self.client_id,
                'Content-Type': 'application/json',
            }

            body = {
                'Keywords': mfg_part_number,
                'Limit': 5,
                'Offset': 0,
                'FilterOptionsRequest': {
                    'ManufacturerFilter': [],
                    'MinimumQuantityAvailable': 1,
                },
                'ExcludeMarketPlaceProducts': True,
            }

            resp = requests.post(self.SEARCH_URL, headers=headers,
                                 json=body, timeout=20)

            if resp.status_code == 429:
                result['error'] = 'Rate limited — try again later'
                return result

            if resp.status_code != 200:
                result['error'] = f'HTTP {resp.status_code}: {resp.text[:200]}'
                return result

            data = resp.json()
            products = data.get('Products', [])

            if not products:
                return result  # found remains False

            # Find the best match — prefer exact manufacturer PN match
            best = None
            for p in products:
                pn = p.get('ManufacturerPartNumber', '')
                if pn.upper() == mfg_part_number.upper():
                    best = p
                    break

            if best is None:
                best = products[0]  # Fall back to first result

            result['found'] = True
            result['digikey_pn'] = best.get('DigiKeyPartNumber', '')
            result['description'] = best.get('Description', {}).get('ProductDescription', '')
            result['manufacturer'] = best.get('Manufacturer', {}).get('Name', '')

            # Extract the lowest unit price from standard pricing tiers
            pricing = best.get('StandardPricing', [])
            if pricing:
                prices = []
                for tier in pricing:
                    try:
                        prices.append(float(tier.get('UnitPrice', 0)))
                    except (ValueError, TypeError):
                        continue
                if prices:
                    result['unit_price'] = min(prices)

        except requests.exceptions.Timeout:
            result['error'] = 'Request timed out'
        except requests.exceptions.ConnectionError:
            result['error'] = 'Connection failed'
        except Exception as e:
            result['error'] = str(e)

        return result


# ============================================================
# Mouser API Client
# ============================================================

class MouserClient:
    """Client for Mouser Search API.

    Uses the keyword search endpoint which handles manufacturer part numbers.
    Authentication uses a Part Search API key passed as a query parameter.

    IMPORTANT: Mouser issues two separate API keys. You must use the
    "Part Search API Key" (not the Order/Cart API key).

    Ref: https://api.mouser.com/api/docs/ui/index
    """

    SEARCH_URL = 'https://api.mouser.com/api/v1/search/keyword'

    def __init__(self, api_key, progress_callback=None):
        self.api_key = api_key
        self._progress_callback = progress_callback

    def is_configured(self):
        """Return True if API key is present."""
        return bool(self.api_key)

    def search_part(self, mfg_part_number, _retry_count=0):
        """Search for a part by manufacturer part number.

        Automatically retries with backoff if rate-limited (up to 3 retries).

        Returns dict with keys:
            found (bool), mouser_pn (str), unit_price (float or None),
            description (str), manufacturer (str), error (str or None)
        """
        MAX_RETRIES = 3

        result = {
            'found': False,
            'mouser_pn': '',
            'unit_price': None,
            'description': '',
            'manufacturer': '',
            'error': None,
        }

        try:
            url = f'{self.SEARCH_URL}?apiKey={self.api_key}'

            body = {
                'SearchByKeywordRequest': {
                    'keyword': mfg_part_number,
                    'records': 10,
                    'startingRecord': 0,
                    'searchOptions': '',
                    'searchWithYourSignUpLanguage': '',
                }
            }

            resp = requests.post(url, json=body, timeout=20,
                                 headers={'Content-Type': 'application/json',
                                          'accept': 'application/json'})

            # Detect rate limiting (Mouser returns 403 or 429)
            if resp.status_code in (429, 403):
                # Check if it's actually a rate limit error
                is_rate_limit = False
                try:
                    err_data = resp.json()
                    errors = err_data.get('Errors', [])
                    for e in errors:
                        if isinstance(e, dict):
                            code = e.get('Code', '')
                            if 'TooMany' in code or 'RateLimit' in code.replace(' ', ''):
                                is_rate_limit = True
                                break
                except Exception:
                    if resp.status_code == 429:
                        is_rate_limit = True

                if is_rate_limit and _retry_count < MAX_RETRIES:
                    # Wait with increasing backoff: 30s, 45s, 60s
                    wait_time = 30 + (_retry_count * 15)
                    if self._progress_callback:
                        self._progress_callback(
                            f"  Mouser: rate limited — waiting {wait_time}s "
                            f"(retry {_retry_count + 1}/{MAX_RETRIES})..."
                        )
                    time.sleep(wait_time)
                    return self.search_part(mfg_part_number, _retry_count + 1)

                if is_rate_limit:
                    result['error'] = (
                        f'Rate limited after {MAX_RETRIES} retries — '
                        f'try again later or reduce batch size'
                    )
                    return result

            if resp.status_code != 200:
                result['error'] = f'HTTP {resp.status_code}: {resp.text[:300]}'
                return result

            data = resp.json()

            # Check for API-level errors
            errors = data.get('Errors', [])
            if errors:
                err_messages = []
                for e in errors:
                    if isinstance(e, dict):
                        msg = e.get('Message', str(e))
                        code = e.get('Code', '')
                        err_messages.append(f"{code}: {msg}" if code else msg)
                    else:
                        err_messages.append(str(e))
                error_text = '; '.join(err_messages)

                # Provide helpful guidance for common errors
                if 'invalid' in error_text.lower() and 'identifier' in error_text.lower():
                    error_text += (
                        ' (Mouser issues TWO API keys — make sure you are using '
                        'the "Part Search API Key", NOT the Order/Cart API key)'
                    )

                result['error'] = error_text
                return result

            parts = data.get('SearchResults', {}).get('Parts', [])

            if not parts:
                return result  # found remains False

            # Find the best match — prefer exact manufacturer PN
            best = None
            for p in parts:
                pn = p.get('ManufacturerPartNumber', '')
                if pn.upper() == mfg_part_number.upper():
                    best = p
                    break

            if best is None:
                best = parts[0]

            result['found'] = True
            result['mouser_pn'] = best.get('MouserPartNumber', '')
            result['description'] = best.get('Description', '')
            result['manufacturer'] = best.get('Manufacturer', '')

            # Extract the lowest unit price from price breaks
            price_breaks = best.get('PriceBreaks', [])
            if price_breaks:
                prices = []
                for pb in price_breaks:
                    price_str = pb.get('Price', '')
                    # Mouser returns price as string like "$0.05" or "0.05"
                    cleaned = price_str.replace('$', '').replace(',', '').strip()
                    try:
                        prices.append(float(cleaned))
                    except (ValueError, TypeError):
                        continue
                if prices:
                    result['unit_price'] = min(prices)

        except requests.exceptions.Timeout:
            result['error'] = 'Request timed out'
        except requests.exceptions.ConnectionError:
            result['error'] = 'Connection failed'
        except Exception as e:
            result['error'] = str(e)

        return result


# ============================================================
# Pricing update engine
# ============================================================

class PricingResult:
    """Result for a single component."""

    def __init__(self, mfg_part_number, manufacturer):
        self.mfg_part_number = mfg_part_number
        self.manufacturer = manufacturer
        self.component_id = None

        # Per-distributor results
        self.digikey = None   # dict from DigiKeyClient.search_part(), or None if skipped
        self.mouser = None    # dict from MouserClient.search_part(), or None if skipped

    @property
    def best_price(self):
        """Return the lowest unit price found across all distributors, or None."""
        prices = []
        if self.digikey and self.digikey.get('unit_price') is not None:
            prices.append(self.digikey['unit_price'])
        if self.mouser and self.mouser.get('unit_price') is not None:
            prices.append(self.mouser['unit_price'])
        return min(prices) if prices else None

    @property
    def best_distributor(self):
        """Return the name of the distributor with the best price."""
        best = self.best_price
        if best is None:
            return None
        if self.digikey and self.digikey.get('unit_price') == best:
            return 'DigiKey'
        if self.mouser and self.mouser.get('unit_price') == best:
            return 'Mouser'
        return None

    @property
    def found_anywhere(self):
        """Return True if at least one distributor had a result."""
        dk = self.digikey and self.digikey.get('found', False)
        mr = self.mouser and self.mouser.get('found', False)
        return dk or mr

    @property
    def status(self):
        """Human-readable status string."""
        if not self.found_anywhere:
            return 'Not Found'
        if self.best_price is not None:
            return f'${self.best_price:.4f} ({self.best_distributor})'
        return 'Found (no pricing)'


def prepare_component_list(db, product_id):
    """Gather unique components from a flattened BOM with their component IDs.

    This performs all database access and should be called on the main thread.

    Args:
        db: BOMDatabase instance
        product_id: assembly to price

    Returns:
        list of dicts with keys: mfg_part_number, manufacturer, component_id
        Empty list if no components found.
    """
    flattened = db.get_flattened_bom(product_id)

    if not flattened:
        return []

    # Deduplicate by mfg_part_number + manufacturer
    seen = set()
    unique_parts = []

    for item in flattened:
        mpn = item['part_number']
        mfr = item['manufacturer']
        key = (mpn.upper(), mfr.upper())
        if key in seen:
            continue
        seen.add(key)

        # Resolve the component_id
        component_id = None
        search_results = db.search_components(mpn)
        for sr in search_results:
            if (sr['mfg_part_number'].upper() == mpn.upper() and
                    sr['manufacturer'].upper() == mfr.upper()):
                component_id = sr['component_id']
                break
        if component_id is None and search_results:
            # Fallback: match on part number only
            for sr in search_results:
                if sr['mfg_part_number'].upper() == mpn.upper():
                    component_id = sr['component_id']
                    break

        unique_parts.append({
            'mfg_part_number': mpn,
            'manufacturer': mfr,
            'component_id': component_id,
        })

    return unique_parts


def prepare_all_components(db):
    """Gather ALL components in the database with their component IDs.

    This performs all database access and should be called on the main thread.

    Args:
        db: BOMDatabase instance

    Returns:
        list of dicts with keys: mfg_part_number, manufacturer, component_id
    """
    all_comps = db.get_all_components()

    parts = []
    for c in all_comps:
        parts.append({
            'mfg_part_number': c['mfg_part_number'],
            'manufacturer': c['manufacturer'],
            'component_id': c['component_id'],
        })

    return parts


def query_pricing(component_list, digikey_client=None,
                  mouser_client=None, progress_callback=None):
    """Query distributor APIs for pricing on a prepared component list.

    This performs only network I/O (no database access) and is safe to
    call from a background thread.

    Args:
        component_list: list from prepare_component_list()
        digikey_client: DigiKeyClient instance (or None to skip DigiKey)
        mouser_client: MouserClient instance (or None to skip Mouser)
        progress_callback: optional callable(message_str) for status updates

    Returns:
        list of PricingResult objects
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    if not HAS_REQUESTS:
        log("ERROR: 'requests' library not installed. Run: pip install requests")
        return []

    if not component_list:
        log("No components found in BOM.")
        return []

    log(f"Found {len(component_list)} unique components to price.\n")

    # Give clients access to the progress callback for retry logging
    if mouser_client:
        mouser_client._progress_callback = progress_callback

    results = []

    for i, part in enumerate(component_list, 1):
        mpn = part['mfg_part_number']
        mfr = part['manufacturer']

        pr = PricingResult(mpn, mfr)
        pr.component_id = part['component_id']

        log(f"[{i}/{len(component_list)}] {mpn} ({mfr})")

        # Query DigiKey
        if digikey_client and digikey_client.is_configured():
            log(f"  DigiKey: searching...")
            pr.digikey = digikey_client.search_part(mpn)
            if pr.digikey['error']:
                log(f"  DigiKey: ERROR \u2014 {pr.digikey['error']}")
            elif pr.digikey['found']:
                price_str = f"${pr.digikey['unit_price']:.4f}" if pr.digikey['unit_price'] else 'no pricing'
                log(f"  DigiKey: found \u2014 {price_str} (PN: {pr.digikey['digikey_pn']})")
            else:
                log(f"  DigiKey: not found")

        # Query Mouser
        if mouser_client and mouser_client.is_configured():
            log(f"  Mouser: searching...")
            pr.mouser = mouser_client.search_part(mpn)
            if pr.mouser['error']:
                log(f"  Mouser: ERROR \u2014 {pr.mouser['error']}")
            elif pr.mouser['found']:
                price_str = f"${pr.mouser['unit_price']:.4f}" if pr.mouser['unit_price'] else 'no pricing'
                log(f"  Mouser: found \u2014 {price_str} (PN: {pr.mouser['mouser_pn']})")
            else:
                log(f"  Mouser: not found")

        if not pr.found_anywhere:
            log(f"  >> Not found at any distributor (existing pricing preserved)")
        else:
            log(f"  >> Best: {pr.status}")

        log("")
        results.append(pr)

        # Delay between queries to respect rate limits
        # Mouser allows ~30 requests/min, DigiKey is more generous.
        # 2.5s base delay keeps us safely under Mouser's limit (~24/min).
        time.sleep(2.5)

    return results


def apply_results_to_database(db, results, progress_callback=None):
    """Write pricing results to the component_sources table.

    Only updates components that were found. Components not found at any
    distributor are left untouched.

    Args:
        db: BOMDatabase instance
        results: list of PricingResult objects
        progress_callback: optional callable(message_str)

    Returns:
        (updated_count, skipped_count)
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)

    updated = 0
    skipped = 0

    for pr in results:
        if pr.component_id is None:
            log(f"SKIP {pr.mfg_part_number}: component_id not found in database")
            skipped += 1
            continue

        if not pr.found_anywhere:
            skipped += 1
            continue

        # Update DigiKey pricing
        if pr.digikey and pr.digikey.get('found') and pr.digikey.get('unit_price') is not None:
            db.add_or_update_component_source(
                pr.component_id,
                'DigiKey',
                pr.digikey.get('digikey_pn', ''),
                pr.digikey['unit_price']
            )
            log(f"Updated {pr.mfg_part_number} — DigiKey: ${pr.digikey['unit_price']:.4f}")
            updated += 1

        # Update Mouser pricing
        if pr.mouser and pr.mouser.get('found') and pr.mouser.get('unit_price') is not None:
            db.add_or_update_component_source(
                pr.component_id,
                'Mouser',
                pr.mouser.get('mouser_pn', ''),
                pr.mouser['unit_price']
            )
            log(f"Updated {pr.mfg_part_number} — Mouser: ${pr.mouser['unit_price']:.4f}")
            updated += 1

    return updated, skipped
