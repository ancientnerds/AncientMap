import { getCountryFlatFlagUrl } from '../../utils/countryFlags'
import './metadata.css'

export type FlagSize = 'sm' | 'md' | 'lg'

interface CountryFlagProps {
  country: string
  size?: FlagSize
  showName?: boolean
}

export function CountryFlag({ country, size = 'sm', showName = false }: CountryFlagProps) {
  const flagUrl = getCountryFlatFlagUrl(country)
  if (!flagUrl) return showName ? <span>{country}</span> : null

  return (
    <>
      <img
        src={flagUrl}
        alt={showName ? '' : country}
        className={`meta-flag meta-flag-${size}`}
      />
      {showName && <span>{country}</span>}
    </>
  )
}
