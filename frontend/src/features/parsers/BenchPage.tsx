/** /parsers/bench: the test bench on its own, against the stored packs. */
import { Link } from '@tanstack/react-router';
import { ArrowLeft, FlaskConical } from 'lucide-react';

import { strings } from '../../strings';
import { PageHeader } from '../shared/PageHeader';
import { TestBench } from './TestBench';
import '../features.css';

export function BenchPage() {
  return (
    <div className="co-page">
      <PageHeader
        icon={FlaskConical}
        title={strings.bench.title}
        lead={strings.bench.lead}
        crumbs={
          <Link to="/parsers" className="co-pagehead__crumb">
            <ArrowLeft size={14} aria-hidden="true" />
            {strings.parsers.detail.back}
          </Link>
        }
      />
      <section className="co-card" aria-label={strings.bench.title}>
        <TestBench />
      </section>
    </div>
  );
}
