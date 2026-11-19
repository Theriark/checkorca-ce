import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

// The generator is plain ESM without dependencies (scripts/openapi-types.mjs).
import { generate, typeOf } from '../../scripts/openapi-types.mjs';

const ROOT = resolve(__dirname, '..', '..');
const OPENAPI = resolve(ROOT, '..', 'docs', 'openapi.json');
const SCHEMA = resolve(ROOT, 'src', 'api', 'schema.d.ts');

describe('api/schema.d.ts', () => {
  it('equals what scripts/openapi-types.mjs generates from docs/openapi.json (run npm run api:types when this fails)', () => {
    const document = JSON.parse(readFileSync(OPENAPI, 'utf8')) as Record<string, unknown>;
    const expected = generate(document);
    const committed = readFileSync(SCHEMA, 'utf8');
    expect(committed).toBe(expected);
  });

  it('maps the schema kinds the API uses', () => {
    expect(typeOf({ type: 'string', enum: ['admin', 'technician'] })).toBe('"admin" | "technician"');
    expect(typeOf({ anyOf: [{ type: 'string', format: 'date-time' }, { type: 'null' }] })).toBe('string | null');
    expect(typeOf({ type: 'array', items: { $ref: '#/components/schemas/UserOut' } })).toBe(
      'components["schemas"]["UserOut"][]',
    );
    expect(typeOf({ type: 'object', properties: { a: { type: 'integer' } }, required: ['a'] })).toBe(
      '{\n  a: number;\n}',
    );
    expect(typeOf({ type: 'object', properties: { b: { type: 'boolean' } } })).toBe('{\n  b?: boolean;\n}');
    expect(typeOf({ type: 'object', additionalProperties: { type: 'string' } })).toBe('Record<string, string>');
  });

  it('refuses a reference outside components.schemas', () => {
    expect(() => typeOf({ $ref: '#/components/responses/X' })).toThrow(/unsupported \$ref/);
  });
});
