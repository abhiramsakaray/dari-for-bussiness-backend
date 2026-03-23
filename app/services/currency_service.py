"""
Currency Service

Maps merchant countries to local currencies and provides
dual-currency conversion helpers (local currency + USDC).
Uses the existing PriceService for exchange rates.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Tuple

from app.services.price_service import get_price_service

logger = logging.getLogger(__name__)


# ── Country → (Currency Code, Currency Symbol, Currency Name) ──
# Covers 100+ countries. Falls back to USD if not found.

COUNTRY_CURRENCY_MAP: Dict[str, Tuple[str, str, str]] = {
    # ── South Asia ──
    "India": ("INR", "₹", "Indian Rupee"),
    "Pakistan": ("PKR", "₨", "Pakistani Rupee"),
    "Bangladesh": ("BDT", "৳", "Bangladeshi Taka"),
    "Sri Lanka": ("LKR", "Rs", "Sri Lankan Rupee"),
    "Nepal": ("NPR", "₨", "Nepalese Rupee"),
    "Bhutan": ("BTN", "Nu", "Bhutanese Ngultrum"),
    "Maldives": ("MVR", "Rf", "Maldivian Rufiyaa"),
    "Afghanistan": ("AFN", "؋", "Afghan Afghani"),

    # ── East Asia ──
    "Japan": ("JPY", "¥", "Japanese Yen"),
    "China": ("CNY", "¥", "Chinese Yuan"),
    "South Korea": ("KRW", "₩", "South Korean Won"),
    "North Korea": ("KPW", "₩", "North Korean Won"),
    "Mongolia": ("MNT", "₮", "Mongolian Tugrik"),
    "Taiwan": ("TWD", "NT$", "New Taiwan Dollar"),
    "Hong Kong": ("HKD", "HK$", "Hong Kong Dollar"),
    "Macau": ("MOP", "MOP$", "Macanese Pataca"),

    # ── Southeast Asia ──
    "Singapore": ("SGD", "S$", "Singapore Dollar"),
    "Malaysia": ("MYR", "RM", "Malaysian Ringgit"),
    "Indonesia": ("IDR", "Rp", "Indonesian Rupiah"),
    "Thailand": ("THB", "฿", "Thai Baht"),
    "Vietnam": ("VND", "₫", "Vietnamese Dong"),
    "Philippines": ("PHP", "₱", "Philippine Peso"),
    "Myanmar": ("MMK", "K", "Myanmar Kyat"),
    "Cambodia": ("KHR", "៛", "Cambodian Riel"),
    "Laos": ("LAK", "₭", "Lao Kip"),
    "Brunei": ("BND", "B$", "Brunei Dollar"),
    "Timor-Leste": ("USD", "$", "US Dollar"),
    "East Timor": ("USD", "$", "US Dollar"),

    # ── Central Asia ──
    "Kazakhstan": ("KZT", "₸", "Kazakhstani Tenge"),
    "Uzbekistan": ("UZS", "сўм", "Uzbekistani Som"),
    "Turkmenistan": ("TMT", "T", "Turkmen Manat"),
    "Kyrgyzstan": ("KGS", "сом", "Kyrgyzstani Som"),
    "Tajikistan": ("TJS", "SM", "Tajikistani Somoni"),

    # ── Middle East ──
    "UAE": ("AED", "د.إ", "UAE Dirham"),
    "United Arab Emirates": ("AED", "د.إ", "UAE Dirham"),
    "Saudi Arabia": ("SAR", "﷼", "Saudi Riyal"),
    "Qatar": ("QAR", "﷼", "Qatari Riyal"),
    "Kuwait": ("KWD", "د.ك", "Kuwaiti Dinar"),
    "Bahrain": ("BHD", "BD", "Bahraini Dinar"),
    "Oman": ("OMR", "﷼", "Omani Rial"),
    "Israel": ("ILS", "₪", "Israeli Shekel"),
    "Turkey": ("TRY", "₺", "Turkish Lira"),
    "Iraq": ("IQD", "ع.د", "Iraqi Dinar"),
    "Iran": ("IRR", "﷼", "Iranian Rial"),
    "Jordan": ("JOD", "JD", "Jordanian Dinar"),
    "Lebanon": ("LBP", "ل.ل", "Lebanese Pound"),
    "Syria": ("SYP", "£S", "Syrian Pound"),
    "Yemen": ("YER", "﷼", "Yemeni Rial"),
    "Palestine": ("ILS", "₪", "Israeli Shekel"),
    "Georgia": ("GEL", "₾", "Georgian Lari"),
    "Armenia": ("AMD", "֏", "Armenian Dram"),
    "Azerbaijan": ("AZN", "₼", "Azerbaijani Manat"),

    # ── Eurozone (EUR) ──
    "Germany": ("EUR", "€", "Euro"),
    "France": ("EUR", "€", "Euro"),
    "Italy": ("EUR", "€", "Euro"),
    "Spain": ("EUR", "€", "Euro"),
    "Netherlands": ("EUR", "€", "Euro"),
    "Belgium": ("EUR", "€", "Euro"),
    "Austria": ("EUR", "€", "Euro"),
    "Portugal": ("EUR", "€", "Euro"),
    "Ireland": ("EUR", "€", "Euro"),
    "Finland": ("EUR", "€", "Euro"),
    "Greece": ("EUR", "€", "Euro"),
    "Luxembourg": ("EUR", "€", "Euro"),
    "Estonia": ("EUR", "€", "Euro"),
    "Latvia": ("EUR", "€", "Euro"),
    "Lithuania": ("EUR", "€", "Euro"),
    "Slovakia": ("EUR", "€", "Euro"),
    "Slovenia": ("EUR", "€", "Euro"),
    "Malta": ("EUR", "€", "Euro"),
    "Cyprus": ("EUR", "€", "Euro"),
    "Croatia": ("EUR", "€", "Euro"),
    "Andorra": ("EUR", "€", "Euro"),
    "Monaco": ("EUR", "€", "Euro"),
    "San Marino": ("EUR", "€", "Euro"),
    "Vatican City": ("EUR", "€", "Euro"),
    "Montenegro": ("EUR", "€", "Euro"),
    "Kosovo": ("EUR", "€", "Euro"),

    # ── Non-Euro Europe ──
    "United Kingdom": ("GBP", "£", "British Pound"),
    "UK": ("GBP", "£", "British Pound"),
    "Switzerland": ("CHF", "CHF", "Swiss Franc"),
    "Liechtenstein": ("CHF", "CHF", "Swiss Franc"),
    "Sweden": ("SEK", "kr", "Swedish Krona"),
    "Norway": ("NOK", "kr", "Norwegian Krone"),
    "Denmark": ("DKK", "kr", "Danish Krone"),
    "Poland": ("PLN", "zł", "Polish Zloty"),
    "Czech Republic": ("CZK", "Kč", "Czech Koruna"),
    "Czechia": ("CZK", "Kč", "Czech Koruna"),
    "Hungary": ("HUF", "Ft", "Hungarian Forint"),
    "Romania": ("RON", "lei", "Romanian Leu"),
    "Bulgaria": ("BGN", "лв", "Bulgarian Lev"),
    "Ukraine": ("UAH", "₴", "Ukrainian Hryvnia"),
    "Russia": ("RUB", "₽", "Russian Ruble"),
    "Serbia": ("RSD", "din", "Serbian Dinar"),
    "Iceland": ("ISK", "kr", "Icelandic Króna"),
    "Albania": ("ALL", "L", "Albanian Lek"),
    "North Macedonia": ("MKD", "ден", "Macedonian Denar"),
    "Bosnia and Herzegovina": ("BAM", "KM", "Convertible Mark"),
    "Moldova": ("MDL", "L", "Moldovan Leu"),
    "Belarus": ("BYN", "Br", "Belarusian Ruble"),

    # ── North America ──
    "United States": ("USD", "$", "US Dollar"),
    "USA": ("USD", "$", "US Dollar"),
    "Canada": ("CAD", "C$", "Canadian Dollar"),
    "Mexico": ("MXN", "$", "Mexican Peso"),

    # ── Central America ──
    "Guatemala": ("GTQ", "Q", "Guatemalan Quetzal"),
    "Belize": ("BZD", "BZ$", "Belize Dollar"),
    "Honduras": ("HNL", "L", "Honduran Lempira"),
    "El Salvador": ("USD", "$", "US Dollar"),
    "Nicaragua": ("NIO", "C$", "Nicaraguan Córdoba"),
    "Costa Rica": ("CRC", "₡", "Costa Rican Colón"),
    "Panama": ("USD", "$", "US Dollar"),

    # ── Caribbean ──
    "Cuba": ("CUP", "₱", "Cuban Peso"),
    "Jamaica": ("JMD", "J$", "Jamaican Dollar"),
    "Haiti": ("HTG", "G", "Haitian Gourde"),
    "Dominican Republic": ("DOP", "RD$", "Dominican Peso"),
    "Trinidad and Tobago": ("TTD", "TT$", "Trinidad Dollar"),
    "Bahamas": ("BSD", "B$", "Bahamian Dollar"),
    "Barbados": ("BBD", "Bds$", "Barbadian Dollar"),
    "Guyana": ("GYD", "G$", "Guyanese Dollar"),
    "Suriname": ("SRD", "Sr$", "Surinamese Dollar"),
    "Antigua and Barbuda": ("XCD", "EC$", "East Caribbean Dollar"),
    "Dominica": ("XCD", "EC$", "East Caribbean Dollar"),
    "Grenada": ("XCD", "EC$", "East Caribbean Dollar"),
    "Saint Kitts and Nevis": ("XCD", "EC$", "East Caribbean Dollar"),
    "Saint Lucia": ("XCD", "EC$", "East Caribbean Dollar"),
    "Saint Vincent and the Grenadines": ("XCD", "EC$", "East Caribbean Dollar"),

    # ── South America ──
    "Brazil": ("BRL", "R$", "Brazilian Real"),
    "Argentina": ("ARS", "$", "Argentine Peso"),
    "Colombia": ("COP", "$", "Colombian Peso"),
    "Chile": ("CLP", "$", "Chilean Peso"),
    "Peru": ("PEN", "S/.", "Peruvian Sol"),
    "Venezuela": ("VES", "Bs.", "Venezuelan Bolívar"),
    "Ecuador": ("USD", "$", "US Dollar"),
    "Uruguay": ("UYU", "$U", "Uruguayan Peso"),
    "Paraguay": ("PYG", "₲", "Paraguayan Guarani"),
    "Bolivia": ("BOB", "Bs.", "Bolivian Boliviano"),

    # ── West Africa ──
    "Nigeria": ("NGN", "₦", "Nigerian Naira"),
    "Ghana": ("GHS", "₵", "Ghanaian Cedi"),
    "Senegal": ("XOF", "CFA", "West African CFA Franc"),
    "Ivory Coast": ("XOF", "CFA", "West African CFA Franc"),
    "Cote d'Ivoire": ("XOF", "CFA", "West African CFA Franc"),
    "Mali": ("XOF", "CFA", "West African CFA Franc"),
    "Burkina Faso": ("XOF", "CFA", "West African CFA Franc"),
    "Niger": ("XOF", "CFA", "West African CFA Franc"),
    "Togo": ("XOF", "CFA", "West African CFA Franc"),
    "Benin": ("XOF", "CFA", "West African CFA Franc"),
    "Guinea-Bissau": ("XOF", "CFA", "West African CFA Franc"),
    "Guinea": ("GNF", "FG", "Guinean Franc"),
    "Sierra Leone": ("SLE", "Le", "Sierra Leonean Leone"),
    "Liberia": ("LRD", "L$", "Liberian Dollar"),
    "Gambia": ("GMD", "D", "Gambian Dalasi"),
    "Cape Verde": ("CVE", "Esc", "Cape Verdean Escudo"),
    "Mauritania": ("MRU", "UM", "Mauritanian Ouguiya"),

    # ── Central Africa ──
    "Cameroon": ("XAF", "FCFA", "Central African CFA Franc"),
    "Central African Republic": ("XAF", "FCFA", "Central African CFA Franc"),
    "Chad": ("XAF", "FCFA", "Central African CFA Franc"),
    "Republic of the Congo": ("XAF", "FCFA", "Central African CFA Franc"),
    "Gabon": ("XAF", "FCFA", "Central African CFA Franc"),
    "Equatorial Guinea": ("XAF", "FCFA", "Central African CFA Franc"),
    "Democratic Republic of the Congo": ("CDF", "FC", "Congolese Franc"),
    "DRC": ("CDF", "FC", "Congolese Franc"),
    "Sao Tome and Principe": ("STN", "Db", "Sao Tomean Dobra"),

    # ── East Africa ──
    "Kenya": ("KES", "KSh", "Kenyan Shilling"),
    "Tanzania": ("TZS", "TSh", "Tanzanian Shilling"),
    "Ethiopia": ("ETB", "Br", "Ethiopian Birr"),
    "Uganda": ("UGX", "USh", "Ugandan Shilling"),
    "Rwanda": ("RWF", "RF", "Rwandan Franc"),
    "Burundi": ("BIF", "FBu", "Burundian Franc"),
    "Somalia": ("SOS", "Sh", "Somali Shilling"),
    "Djibouti": ("DJF", "Fdj", "Djiboutian Franc"),
    "Eritrea": ("ERN", "Nfk", "Eritrean Nakfa"),
    "South Sudan": ("SSP", "£", "South Sudanese Pound"),
    "Sudan": ("SDG", "£", "Sudanese Pound"),
    "Madagascar": ("MGA", "Ar", "Malagasy Ariary"),
    "Mauritius": ("MUR", "₨", "Mauritian Rupee"),
    "Seychelles": ("SCR", "₨", "Seychellois Rupee"),
    "Comoros": ("KMF", "CF", "Comorian Franc"),

    # ── Southern Africa ──
    "South Africa": ("ZAR", "R", "South African Rand"),
    "Zimbabwe": ("ZWL", "Z$", "Zimbabwean Dollar"),
    "Mozambique": ("MZN", "MT", "Mozambican Metical"),
    "Angola": ("AOA", "Kz", "Angolan Kwanza"),
    "Zambia": ("ZMW", "ZK", "Zambian Kwacha"),
    "Malawi": ("MWK", "MK", "Malawian Kwacha"),
    "Botswana": ("BWP", "P", "Botswana Pula"),
    "Namibia": ("NAD", "N$", "Namibian Dollar"),
    "Lesotho": ("LSL", "L", "Lesotho Loti"),
    "Eswatini": ("SZL", "E", "Swazi Lilangeni"),
    "Swaziland": ("SZL", "E", "Swazi Lilangeni"),

    # ── North Africa ──
    "Egypt": ("EGP", "E£", "Egyptian Pound"),
    "Morocco": ("MAD", "MAD", "Moroccan Dirham"),
    "Tunisia": ("TND", "DT", "Tunisian Dinar"),
    "Algeria": ("DZD", "د.ج", "Algerian Dinar"),
    "Libya": ("LYD", "LD", "Libyan Dinar"),

    # ── Oceania ──
    "Australia": ("AUD", "A$", "Australian Dollar"),
    "New Zealand": ("NZD", "NZ$", "New Zealand Dollar"),
    "Fiji": ("FJD", "FJ$", "Fijian Dollar"),
    "Papua New Guinea": ("PGK", "K", "Papua New Guinean Kina"),
    "Samoa": ("WST", "WS$", "Samoan Tala"),
    "Tonga": ("TOP", "T$", "Tongan Paanga"),
    "Vanuatu": ("VUV", "VT", "Vanuatu Vatu"),
    "Solomon Islands": ("SBD", "SI$", "Solomon Islands Dollar"),
    "Kiribati": ("AUD", "A$", "Australian Dollar"),
    "Marshall Islands": ("USD", "$", "US Dollar"),
    "Micronesia": ("USD", "$", "US Dollar"),
    "Palau": ("USD", "$", "US Dollar"),
    "Tuvalu": ("AUD", "A$", "Australian Dollar"),
    "Nauru": ("AUD", "A$", "Australian Dollar"),
}

# Default fallback
DEFAULT_CURRENCY = ("USD", "$", "US Dollar")


def get_currency_for_country(country: Optional[str]) -> Tuple[str, str, str]:
    """
    Get (currency_code, symbol, name) for a country name.
    Falls back to USD if country is None or not found.
    """
    if not country:
        return DEFAULT_CURRENCY

    # Try exact match first
    result = COUNTRY_CURRENCY_MAP.get(country)
    if result:
        return result

    # Case-insensitive match
    country_lower = country.lower().strip()
    for key, value in COUNTRY_CURRENCY_MAP.items():
        if key.lower() == country_lower:
            return value

    # Partial match (e.g. "United States of America" → "United States")
    for key, value in COUNTRY_CURRENCY_MAP.items():
        if key.lower() in country_lower or country_lower in key.lower():
            return value

    return DEFAULT_CURRENCY


async def convert_usdc_to_local(
    amount_usdc: float,
    currency_code: str,
) -> Tuple[float, float]:
    """
    Convert a USDC amount to local currency.

    Returns (local_amount, exchange_rate).
    Rate = how many local currency units per 1 USDC.
    """
    if currency_code == "USD":
        return amount_usdc, 1.0

    try:
        price_service = get_price_service()
        # USDC ≈ 1 USD, so we just need USD → local rate
        rate = await price_service.get_fiat_rate("USD", currency_code)
        local_amount = float(
            (Decimal(str(amount_usdc)) * rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        return local_amount, float(rate)
    except Exception as e:
        logger.error(f"Currency conversion error ({currency_code}): {e}")
        return amount_usdc, 1.0


async def convert_local_to_usdc(
    amount_local: float,
    currency_code: str,
) -> Tuple[float, float]:
    """
    Convert local fiat amount to USDC.

    Returns (amount_usdc, exchange_rate).
    exchange_rate = local units per 1 USD/USDC.
    """
    if currency_code == "USD":
        return amount_local, 1.0

    try:
        price_service = get_price_service()
        # rate is local units per 1 USD
        rate = await price_service.get_fiat_rate("USD", currency_code)
        if not rate or rate <= 0:
            raise ValueError(f"Invalid rate for {currency_code}: {rate}")

        usdc_amount = float(
            (Decimal(str(amount_local)) / rate).quantize(
                Decimal("0.00000001"), rounding=ROUND_HALF_UP
            )
        )
        return usdc_amount, float(rate)
    except Exception as e:
        logger.error(f"Local->USDC conversion error ({currency_code}): {e}")
        # Safe fallback keeps prior behavior
        return amount_local, 1.0


async def build_local_amount(
    amount_usdc: float,
    currency_code: str,
    currency_symbol: str,
) -> dict:
    """
    Build a dict with both USDC and local currency representation.

    Returns:
        {
            "amount_usdc": 50.0,
            "amount_local": 4150.00,
            "local_currency": "INR",
            "local_symbol": "₹",
            "exchange_rate": 83.0,
            "display_local": "₹4,150.00"
        }
    """
    local_amount, rate = await convert_usdc_to_local(amount_usdc, currency_code)

    # Format display string
    if currency_code == "JPY" or currency_code == "KRW":
        display = f"{currency_symbol}{local_amount:,.0f}"
    else:
        display = f"{currency_symbol}{local_amount:,.2f}"

    return {
        "amount_usdc": round(amount_usdc, 8),
        "amount_local": local_amount,
        "local_currency": currency_code,
        "local_symbol": currency_symbol,
        "exchange_rate": rate,
        "display_local": display,
    }
