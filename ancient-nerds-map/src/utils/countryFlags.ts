// Continent definitions for grouping
export type Continent = 'Europe' | 'Asia' | 'Africa' | 'Americas' | 'Oceania' | 'Middle East'

// ISO code → Continent mapping
const CODE_TO_CONTINENT: Record<string, Continent> = {
  // Middle East
  EG: 'Middle East', IQ: 'Middle East', IR: 'Middle East', SY: 'Middle East', JO: 'Middle East',
  IL: 'Middle East', LB: 'Middle East', TR: 'Middle East', SA: 'Middle East', YE: 'Middle East',
  OM: 'Middle East', AE: 'Middle East', KW: 'Middle East', BH: 'Middle East', QA: 'Middle East',
  PS: 'Middle East', CY: 'Middle East',
  // Europe
  GR: 'Europe', IT: 'Europe', ES: 'Europe', FR: 'Europe', PT: 'Europe', GB: 'Europe', IE: 'Europe',
  DE: 'Europe', AT: 'Europe', CH: 'Europe', NL: 'Europe', BE: 'Europe', LU: 'Europe', DK: 'Europe',
  SE: 'Europe', NO: 'Europe', FI: 'Europe', IS: 'Europe', PL: 'Europe', CZ: 'Europe', SK: 'Europe',
  HU: 'Europe', RO: 'Europe', BG: 'Europe', RS: 'Europe', HR: 'Europe', SI: 'Europe', BA: 'Europe',
  ME: 'Europe', MK: 'Europe', AL: 'Europe', XK: 'Europe', MD: 'Europe', UA: 'Europe', BY: 'Europe',
  LT: 'Europe', LV: 'Europe', EE: 'Europe', MT: 'Europe', MC: 'Europe', AD: 'Europe', SM: 'Europe',
  VA: 'Europe', LI: 'Europe', RU: 'Europe', GE: 'Europe', AM: 'Europe', AZ: 'Europe',
  FO: 'Europe', GI: 'Europe', SJ: 'Europe', AX: 'Europe', JE: 'Europe', GG: 'Europe', IM: 'Europe', BALTIC: 'Europe',
  // Asia
  CN: 'Asia', JP: 'Asia', KR: 'Asia', KP: 'Asia', TW: 'Asia', MN: 'Asia', VN: 'Asia', TH: 'Asia',
  MM: 'Asia', KH: 'Asia', LA: 'Asia', MY: 'Asia', SG: 'Asia', ID: 'Asia', PH: 'Asia', BN: 'Asia',
  TL: 'Asia', IN: 'Asia', PK: 'Asia', BD: 'Asia', LK: 'Asia', NP: 'Asia', BT: 'Asia', MV: 'Asia',
  AF: 'Asia', KZ: 'Asia', UZ: 'Asia', TM: 'Asia', TJ: 'Asia', KG: 'Asia', HK: 'Asia', MO: 'Asia',
  // Africa
  MA: 'Africa', DZ: 'Africa', TN: 'Africa', LY: 'Africa', SD: 'Africa', SS: 'Africa', ET: 'Africa',
  ER: 'Africa', DJ: 'Africa', SO: 'Africa', KE: 'Africa', TZ: 'Africa', UG: 'Africa', RW: 'Africa',
  BI: 'Africa', CD: 'Africa', CG: 'Africa', GA: 'Africa', GQ: 'Africa', CM: 'Africa', CF: 'Africa',
  TD: 'Africa', NE: 'Africa', NG: 'Africa', BJ: 'Africa', TG: 'Africa', GH: 'Africa', CI: 'Africa',
  LR: 'Africa', SL: 'Africa', GN: 'Africa', GW: 'Africa', SN: 'Africa', GM: 'Africa', MR: 'Africa',
  ML: 'Africa', BF: 'Africa', CV: 'Africa', AO: 'Africa', ZM: 'Africa', ZW: 'Africa', MW: 'Africa',
  MZ: 'Africa', BW: 'Africa', NA: 'Africa', ZA: 'Africa', LS: 'Africa', SZ: 'Africa', MG: 'Africa',
  MU: 'Africa', SC: 'Africa', KM: 'Africa', RE: 'Africa', YT: 'Africa', SH: 'Africa',
  // Americas
  US: 'Americas', CA: 'Americas', MX: 'Americas', GT: 'Americas', BZ: 'Americas', HN: 'Americas',
  SV: 'Americas', NI: 'Americas', CR: 'Americas', PA: 'Americas', CU: 'Americas', JM: 'Americas',
  HT: 'Americas', DO: 'Americas', PR: 'Americas', BS: 'Americas', TT: 'Americas', BB: 'Americas',
  CO: 'Americas', VE: 'Americas', EC: 'Americas', PE: 'Americas', BO: 'Americas', BR: 'Americas',
  PY: 'Americas', UY: 'Americas', AR: 'Americas', CL: 'Americas', GY: 'Americas', SR: 'Americas',
  GF: 'Americas', BM: 'Americas', KY: 'Americas', VG: 'Americas', VI: 'Americas', AW: 'Americas',
  CW: 'Americas', SX: 'Americas', TC: 'Americas', AI: 'Americas', MS: 'Americas', FK: 'Americas',
  GS: 'Americas', PM: 'Americas', MQ: 'Americas', GP: 'Americas', GL: 'Americas',
  // Oceania
  AU: 'Oceania', NZ: 'Oceania', PG: 'Oceania', FJ: 'Oceania', SB: 'Oceania', VU: 'Oceania',
  WS: 'Oceania', TO: 'Oceania', FM: 'Oceania', PW: 'Oceania', MH: 'Oceania', KI: 'Oceania',
  NR: 'Oceania', TV: 'Oceania', MP: 'Oceania', GU: 'Oceania', PF: 'Oceania', NC: 'Oceania',
  WF: 'Oceania', AS: 'Oceania', CK: 'Oceania', NU: 'Oceania', TK: 'Oceania', NF: 'Oceania',
  CX: 'Oceania', CC: 'Oceania', PN: 'Oceania',
}

// Country name → ISO 3166-1 alpha-2 code mapping
const COUNTRY_CODES: Record<string, string> = {
  // Middle East & Near East (important for archaeology)
  'Egypt': 'EG',
  'Iraq': 'IQ',
  'Iran': 'IR',
  'Syria': 'SY',
  'Jordan': 'JO',
  'Israel': 'IL',
  'Lebanon': 'LB',
  'Turkey': 'TR',
  'Saudi Arabia': 'SA',
  'Yemen': 'YE',
  'Oman': 'OM',
  'United Arab Emirates': 'AE',
  'Kuwait': 'KW',
  'Bahrain': 'BH',
  'Qatar': 'QA',
  'Palestine': 'PS',
  'Cyprus': 'CY',

  // Mediterranean & Europe
  'Greece': 'GR',
  'Italy': 'IT',
  'Spain': 'ES',
  'France': 'FR',
  'Portugal': 'PT',
  'United Kingdom': 'GB',
  'UK': 'GB',
  'England': 'GB',
  'Scotland': 'GB',
  'Wales': 'GB',
  'Ireland': 'IE',
  'Germany': 'DE',
  'Austria': 'AT',
  'Switzerland': 'CH',
  'Netherlands': 'NL',
  'Belgium': 'BE',
  'Luxembourg': 'LU',
  'Denmark': 'DK',
  'Sweden': 'SE',
  'Norway': 'NO',
  'Finland': 'FI',
  'Iceland': 'IS',
  'Poland': 'PL',
  'Czech Republic': 'CZ',
  'Czechia': 'CZ',
  'Slovakia': 'SK',
  'Hungary': 'HU',
  'Romania': 'RO',
  'Bulgaria': 'BG',
  'Serbia': 'RS',
  'Croatia': 'HR',
  'Slovenia': 'SI',
  'Bosnia and Herzegovina': 'BA',
  'Montenegro': 'ME',
  'North Macedonia': 'MK',
  'Macedonia': 'MK',
  'Albania': 'AL',
  'Kosovo': 'XK',
  'Moldova': 'MD',
  'Ukraine': 'UA',
  'Belarus': 'BY',
  'Lithuania': 'LT',
  'Latvia': 'LV',
  'Estonia': 'EE',
  'Malta': 'MT',
  'Monaco': 'MC',
  'Andorra': 'AD',
  'San Marino': 'SM',
  'Vatican City': 'VA',
  'Liechtenstein': 'LI',

  // Asia
  'China': 'CN',
  'Japan': 'JP',
  'South Korea': 'KR',
  'Korea': 'KR',
  'North Korea': 'KP',
  'Taiwan': 'TW',
  'Mongolia': 'MN',
  'Vietnam': 'VN',
  'Thailand': 'TH',
  'Myanmar': 'MM',
  'Burma': 'MM',
  'Cambodia': 'KH',
  'Laos': 'LA',
  'Malaysia': 'MY',
  'Singapore': 'SG',
  'Indonesia': 'ID',
  'Philippines': 'PH',
  'Brunei': 'BN',
  'East Timor': 'TL',
  'Timor-Leste': 'TL',

  // South Asia
  'India': 'IN',
  'Pakistan': 'PK',
  'Bangladesh': 'BD',
  'Sri Lanka': 'LK',
  'Nepal': 'NP',
  'Bhutan': 'BT',
  'Maldives': 'MV',
  'Afghanistan': 'AF',

  // Central Asia
  'Kazakhstan': 'KZ',
  'Uzbekistan': 'UZ',
  'Turkmenistan': 'TM',
  'Tajikistan': 'TJ',
  'Kyrgyzstan': 'KG',

  // Russia & Caucasus
  'Russia': 'RU',
  'Georgia': 'GE',
  'Georgia (Country)': 'GE', // Disambiguation from US state
  'Armenia': 'AM',
  'Azerbaijan': 'AZ',

  // Africa
  'Morocco': 'MA',
  'Algeria': 'DZ',
  'Tunisia': 'TN',
  'Libya': 'LY',
  'Sudan': 'SD',
  'South Sudan': 'SS',
  'Ethiopia': 'ET',
  'Eritrea': 'ER',
  'Djibouti': 'DJ',
  'Somalia': 'SO',
  'Kenya': 'KE',
  'Tanzania': 'TZ',
  'Uganda': 'UG',
  'Rwanda': 'RW',
  'Burundi': 'BI',
  'Democratic Republic of the Congo': 'CD',
  'DRC': 'CD',
  'Congo': 'CG',
  'Republic of the Congo': 'CG',
  'Gabon': 'GA',
  'Equatorial Guinea': 'GQ',
  'Cameroon': 'CM',
  'Central African Republic': 'CF',
  'Chad': 'TD',
  'Niger': 'NE',
  'Nigeria': 'NG',
  'Benin': 'BJ',
  'Togo': 'TG',
  'Ghana': 'GH',
  'Ivory Coast': 'CI',
  "Côte d'Ivoire": 'CI',
  'Liberia': 'LR',
  'Sierra Leone': 'SL',
  'Guinea': 'GN',
  'Guinea-Bissau': 'GW',
  'Senegal': 'SN',
  'Gambia': 'GM',
  'The Gambia': 'GM',
  'Republic of the Gambia': 'GM',
  'Mauritania': 'MR',
  'Mali': 'ML',
  'Burkina Faso': 'BF',
  'Cape Verde': 'CV',
  'Cabo Verde': 'CV',
  'Angola': 'AO',
  'Zambia': 'ZM',
  'Zimbabwe': 'ZW',
  'Malawi': 'MW',
  'Mozambique': 'MZ',
  'Botswana': 'BW',
  'Namibia': 'NA',
  'South Africa': 'ZA',
  'Lesotho': 'LS',
  'Eswatini': 'SZ',
  'Swaziland': 'SZ',
  'Madagascar': 'MG',
  'Mauritius': 'MU',
  'Seychelles': 'SC',
  'Comoros': 'KM',

  // Americas
  'United States': 'US',
  'USA': 'US',
  'Canada': 'CA',
  'Mexico': 'MX',
  'Guatemala': 'GT',
  'Belize': 'BZ',
  'Honduras': 'HN',
  'El Salvador': 'SV',
  'Nicaragua': 'NI',
  'Costa Rica': 'CR',
  'Panama': 'PA',
  'Cuba': 'CU',
  'Jamaica': 'JM',
  'Haiti': 'HT',
  'Dominican Republic': 'DO',
  'Puerto Rico': 'PR',
  'Bahamas': 'BS',
  'Trinidad and Tobago': 'TT',
  'Barbados': 'BB',
  'Colombia': 'CO',
  'Venezuela': 'VE',
  'Ecuador': 'EC',
  'Peru': 'PE',
  'Bolivia': 'BO',
  'Brazil': 'BR',
  'Paraguay': 'PY',
  'Uruguay': 'UY',
  'Argentina': 'AR',
  'Chile': 'CL',
  'Guyana': 'GY',
  'Suriname': 'SR',
  'French Guiana': 'GF',

  // Oceania
  'Australia': 'AU',
  'New Zealand': 'NZ',
  'Papua New Guinea': 'PG',
  'Fiji': 'FJ',
  'Solomon Islands': 'SB',
  'Vanuatu': 'VU',
  'Samoa': 'WS',
  'Tonga': 'TO',
  'Micronesia': 'FM',
  'Palau': 'PW',
  'Marshall Islands': 'MH',
  'Kiribati': 'KI',
  'Nauru': 'NR',
  'Tuvalu': 'TV',
  'Northern Mariana Islands': 'MP',
  'Guam': 'GU',

  // Special regions (non-country)
  'Baltic Sea': 'BALTIC', // United Baltic Duchy flag

  // Territories & Dependencies
  'Greenland': 'GL',
  'Easter Island': 'CL', // Territory of Chile
  'Faroe Islands': 'FO',
  'Gibraltar': 'GI',
  'Bermuda': 'BM',
  'Cayman Islands': 'KY',
  'British Virgin Islands': 'VG',
  'US Virgin Islands': 'VI',
  'Aruba': 'AW',
  'Curaçao': 'CW',
  'Sint Maarten': 'SX',
  'Turks and Caicos Islands': 'TC',
  'Anguilla': 'AI',
  'Montserrat': 'MS',
  'Saint Helena': 'SH',
  'Falkland Islands': 'FK',
  'South Georgia': 'GS',
  'French Polynesia': 'PF',
  'New Caledonia': 'NC',
  'Wallis and Futuna': 'WF',
  'Saint Pierre and Miquelon': 'PM',
  'Réunion': 'RE',
  'Martinique': 'MQ',
  'Guadeloupe': 'GP',
  'Mayotte': 'YT',
  'American Samoa': 'AS',
  'Cook Islands': 'CK',
  'Niue': 'NU',
  'Tokelau': 'TK',
  'Norfolk Island': 'NF',
  'Christmas Island': 'CX',
  'Cocos Islands': 'CC',
  'Pitcairn Islands': 'PN',
  'Svalbard': 'SJ',
  'Åland Islands': 'AX',
  'Jersey': 'JE',
  'Guernsey': 'GG',
  'Isle of Man': 'IM',
  'Hong Kong': 'HK',
  'Macau': 'MO',
}

/** Extract country from a location string (last part after comma) */
function extractCountryFromLocation(location: string): string {
  if (!location) return ''
  const parts = location.split(',')
  return parts[parts.length - 1].trim()
}

/** Get the country code for a country name or location string (internal use) */
function getCountryCode(countryOrLocation: string): string | null {
  if (!countryOrLocation) return null

  // Try exact match first (for country name)
  const code = COUNTRY_CODES[countryOrLocation]
  if (code) {
    return code
  }

  // Try case-insensitive match
  const lowerInput = countryOrLocation.toLowerCase()
  for (const [name, countryCode] of Object.entries(COUNTRY_CODES)) {
    if (name.toLowerCase() === lowerInput) {
      return countryCode
    }
  }

  // If input contains comma, extract country from location string
  if (countryOrLocation.includes(',')) {
    const extracted = extractCountryFromLocation(countryOrLocation)
    if (extracted) {
      const extractedCode = COUNTRY_CODES[extracted]
      if (extractedCode) return extractedCode

      // Try case-insensitive on extracted
      const lowerExtracted = extracted.toLowerCase()
      for (const [name, countryCode] of Object.entries(COUNTRY_CODES)) {
        if (name.toLowerCase() === lowerExtracted) {
          return countryCode
        }
      }
    }
  }

  return null
}

/** Get the flag image URL for a country name (h60 flat flags) */
export function getCountryFlatFlagUrl(country: string): string | null {
  const code = getCountryCode(country)
  return code ? `/flags-flat/${code.toLowerCase()}.webp` : null
}

/** Get the continent for a country name */
export function getCountryContinent(country: string): Continent | null {
  const code = getCountryCode(country)
  return code ? CODE_TO_CONTINENT[code] || null : null
}

/** Continent display order */
export const CONTINENT_ORDER: Continent[] = ['Europe', 'Middle East', 'Asia', 'Africa', 'Americas', 'Oceania']
