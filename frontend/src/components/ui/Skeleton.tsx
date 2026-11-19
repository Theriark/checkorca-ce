import type { CSSProperties } from 'react';

import { strings } from '../../strings';
import './ui.css';

export interface SkeletonProps {
  readonly width?: number | string;
  readonly height?: number | string;
  readonly radius?: 'sm' | 'md' | 'pill' | 'circle';
  readonly className?: string;
}

/** A shimmering placeholder block. Hidden from assistive technology; wrap a
 *  group in <SkeletonGroup> to announce one "Loading" instead. */
export function Skeleton({ width = '100%', height = 16, radius = 'sm', className }: SkeletonProps) {
  const style: CSSProperties = { width, height };
  const classes = ['co-skeleton', `co-skeleton--${radius}`];
  if (className) {
    classes.push(className);
  }
  return <span className={classes.join(' ')} style={style} aria-hidden="true" />;
}

export interface SkeletonGroupProps {
  readonly label?: string;
  readonly className?: string;
  readonly children: React.ReactNode;
}

export function SkeletonGroup({ label = strings.states.loading, className, children }: SkeletonGroupProps) {
  return (
    <div className={className} role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** Lines of text while a paragraph loads. */
export function SkeletonText({ lines = 3 }: { readonly lines?: number }) {
  return (
    <div className="co-skeleton-text">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} height={14} width={index === lines - 1 ? '60%' : '100%'} />
      ))}
    </div>
  );
}
