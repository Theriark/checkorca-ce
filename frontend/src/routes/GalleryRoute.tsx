/**
 * The /_gallery route component. In the test build (VITE_GALLERY=1) it loads
 * GalleryPage on demand; in the product build it is the 404 page and the
 * gallery chunk is never emitted (scripts/check-product-bundle.mjs proves it
 * after every product build).
 */
import { Suspense, lazy } from 'react';

import { NotFoundPage } from './NotFoundPage';

export const GALLERY_ENABLED = import.meta.env.VITE_GALLERY === '1';

const GalleryPage = GALLERY_ENABLED
  ? lazy(() => import('./GalleryPage').then((module) => ({ default: module.GalleryPage })))
  : NotFoundPage;

export function GalleryRoute() {
  return (
    <Suspense fallback={null}>
      <GalleryPage />
    </Suspense>
  );
}
