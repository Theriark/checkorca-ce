import { PRODUCT_NAME } from '../strings';
import { useTheme } from '../theme/useTheme';

const BRAND = '/brand';

export interface LogoProps {
  /** 'horizontal' for the header, 'stacked' for sign-in and first run. */
  readonly variant: 'horizontal' | 'stacked';
  /** Rendered width in CSS pixels; the files carry 2x copies for sharpness. */
  readonly width: number;
  readonly className?: string;
}

/**
 * The brand lockups, byte for byte from frontend/public/brand. The PNGs have
 * an opaque tile in the page colour (off-white light, ink dark), so the light
 * and dark files follow the theme in effect and sit on a surface of the same
 * colour. The mark is never redrawn, recoloured or cropped.
 */
export function Logo({ variant, width, className }: LogoProps) {
  const { theme } = useTheme();
  const dark = theme === 'dark';
  if (variant === 'stacked') {
    const base = dark ? 'logo-stacked-dark' : 'logo-stacked';
    return (
      <img
        className={className}
        src={`${BRAND}/${base}-400x400.png`}
        srcSet={`${BRAND}/${base}-400x400.png 1x, ${BRAND}/${base}-800x800.png 2x`}
        alt={PRODUCT_NAME}
        width={width}
        height={width}
        decoding="async"
      />
    );
  }
  const base = dark ? 'logo-horizontal-dark' : 'logo-horizontal';
  return (
    <img
      className={className}
      src={`${BRAND}/${base}-600x200.png`}
      srcSet={`${BRAND}/${base}-600x200.png 1x, ${BRAND}/${base}-1200x400.png 2x`}
      alt={PRODUCT_NAME}
      width={width}
      height={Math.round(width / 3)}
      decoding="async"
    />
  );
}
