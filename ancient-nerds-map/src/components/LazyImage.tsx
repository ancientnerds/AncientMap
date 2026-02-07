import { forwardRef, useCallback, useRef, type ImgHTMLAttributes } from 'react'
import './LazyImage.css'

interface LazyImageProps extends ImgHTMLAttributes<HTMLImageElement> {
  /** When true, hidden state uses opacity-only (no max-height:0). For absolute-positioned images. */
  overlay?: boolean
  /** If set, image switches to this src on error before calling onError. */
  fallbackSrc?: string
}

const LazyImage = forwardRef<HTMLImageElement, LazyImageProps>(
  ({ overlay, fallbackSrc, className, onLoad, onError, loading = 'lazy', ...rest }, ref) => {
    const imgRef = useRef<HTMLImageElement | null>(null)
    const triedFallback = useRef(false)

    const setRef = useCallback(
      (el: HTMLImageElement | null) => {
        imgRef.current = el
        if (typeof ref === 'function') ref(el)
        else if (ref) (ref as React.MutableRefObject<HTMLImageElement | null>).current = el
      },
      [ref],
    )

    const hiddenClass = overlay ? 'lazy-image--hidden-overlay' : 'lazy-image--hidden'

    const handleLoad = useCallback(
      (e: React.SyntheticEvent<HTMLImageElement>) => {
        const el = e.currentTarget
        el.classList.remove('lazy-image--hidden', 'lazy-image--hidden-overlay')
        el.classList.add('lazy-image--tv-on')
        onLoad?.(e)
      },
      [onLoad],
    )

    const handleError = useCallback(
      (e: React.SyntheticEvent<HTMLImageElement>) => {
        const el = e.currentTarget
        el.classList.remove('lazy-image--hidden', 'lazy-image--hidden-overlay')

        if (fallbackSrc && !triedFallback.current) {
          triedFallback.current = true
          el.src = fallbackSrc
          return
        }
        onError?.(e)
      },
      [fallbackSrc, onError],
    )

    return (
      <img
        ref={setRef}
        className={`${hiddenClass}${className ? ` ${className}` : ''}`}
        loading={loading}
        onLoad={handleLoad}
        onError={handleError}
        {...rest}
      />
    )
  },
)

LazyImage.displayName = 'LazyImage'
export default LazyImage
