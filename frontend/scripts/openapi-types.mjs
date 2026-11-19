#!/usr/bin/env node
/**
 * Generates src/api/schema.d.ts from docs/openapi.json.
 *
 *   npm run api:types
 *
 * Why an own script: openapi-typescript 7 declares a peer dependency on
 * TypeScript 5 and the repository pins TypeScript 6. The API is small and
 * regular (FastAPI output), so a dependency-free generator covers it: object,
 * array, enum, anyOf and $ref schemas, path and query parameters, request
 * bodies and responses by status and media type. src/api/schema.test.ts
 * regenerates the file in memory and fails when the committed one is stale.
 */
import { readFileSync, writeFileSync } from 'node:fs';

const INDENT = '  ';

function quote(name) {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name) ? name : JSON.stringify(name);
}

function refName(ref) {
  const prefix = '#/components/schemas/';
  if (!ref.startsWith(prefix)) {
    throw new Error(`unsupported $ref ${ref}`);
  }
  return `components["schemas"][${JSON.stringify(ref.slice(prefix.length))}]`;
}

/** The TypeScript type of a JSON schema (OpenAPI 3.1 subset). */
export function typeOf(schema, depth = 0) {
  if (schema === undefined || schema === true) {
    return 'unknown';
  }
  if (schema === false) {
    return 'never';
  }
  if (schema.$ref) {
    return refName(schema.$ref);
  }
  if (schema.const !== undefined) {
    return JSON.stringify(schema.const);
  }
  if (schema.enum) {
    return schema.enum.map((value) => JSON.stringify(value)).join(' | ');
  }
  if (schema.anyOf) {
    return schema.anyOf.map((item) => typeOf(item, depth)).join(' | ');
  }
  if (schema.oneOf) {
    return schema.oneOf.map((item) => typeOf(item, depth)).join(' | ');
  }
  if (schema.allOf) {
    return schema.allOf.map((item) => `(${typeOf(item, depth)})`).join(' & ');
  }
  const kinds = Array.isArray(schema.type) ? schema.type : [schema.type];
  const parts = kinds.map((kind) => {
    switch (kind) {
      case 'string':
        return 'string';
      case 'integer':
      case 'number':
        return 'number';
      case 'boolean':
        return 'boolean';
      case 'null':
        return 'null';
      case 'array':
        return `${wrap(typeOf(schema.items, depth))}[]`;
      case 'object':
      case undefined:
        return objectType(schema, depth);
      default:
        throw new Error(`unsupported schema type ${kind}`);
    }
  });
  return parts.join(' | ');
}

function wrap(type) {
  return /[|&]/.test(type) ? `(${type})` : type;
}

function objectType(schema, depth) {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const names = Object.keys(properties);
  if (names.length === 0) {
    if (schema.additionalProperties === false) {
      return 'Record<string, never>';
    }
    const extra = schema.additionalProperties;
    return extra && extra !== true ? `Record<string, ${typeOf(extra, depth)}>` : 'Record<string, unknown>';
  }
  const pad = INDENT.repeat(depth + 1);
  const lines = names.map((name) => {
    const property = properties[name];
    const optional = required.has(name) ? '' : '?';
    const doc = property.description ? `${pad}/** ${property.description} */\n` : '';
    return `${doc}${pad}${quote(name)}${optional}: ${typeOf(property, depth + 1)};`;
  });
  if (schema.additionalProperties && schema.additionalProperties !== false) {
    const extra = schema.additionalProperties === true ? 'unknown' : typeOf(schema.additionalProperties, depth + 1);
    lines.push(`${pad}[key: string]: ${extra};`);
  }
  return `{\n${lines.join('\n')}\n${INDENT.repeat(depth)}}`;
}

function parameterBlock(parameters, where, depth) {
  const own = parameters.filter((parameter) => parameter.in === where);
  if (own.length === 0) {
    return 'never';
  }
  const pad = INDENT.repeat(depth + 1);
  const lines = own.map(
    (parameter) =>
      `${pad}${quote(parameter.name)}${parameter.required ? '' : '?'}: ${typeOf(parameter.schema, depth + 1)};`,
  );
  return `{\n${lines.join('\n')}\n${INDENT.repeat(depth)}}`;
}

function contentBlock(content, depth) {
  if (!content) {
    return 'never';
  }
  const pad = INDENT.repeat(depth + 1);
  const lines = Object.entries(content).map(
    ([media, body]) => `${pad}${quote(media)}: ${typeOf(body.schema, depth + 1)};`,
  );
  return `{\n${lines.join('\n')}\n${INDENT.repeat(depth)}}`;
}

function operationType(operation, pathParameters, depth) {
  const pad = INDENT.repeat(depth + 1);
  const parameters = [...(pathParameters ?? []), ...(operation.parameters ?? [])];
  const lines = [];
  if (operation.summary) {
    lines.push(`${pad}/** ${operation.summary} */`);
  }
  lines.push(`${pad}parameters: {`);
  lines.push(`${pad}${INDENT}query: ${parameterBlock(parameters, 'query', depth + 2)};`);
  lines.push(`${pad}${INDENT}path: ${parameterBlock(parameters, 'path', depth + 2)};`);
  lines.push(`${pad}};`);
  const body = operation.requestBody;
  lines.push(
    `${pad}requestBody${body?.required ? '' : '?'}: ${body ? `{\n${pad}${INDENT}content: ${contentBlock(body.content, depth + 2)};\n${pad}}` : 'never'};`,
  );
  lines.push(`${pad}responses: {`);
  for (const [status, response] of Object.entries(operation.responses ?? {})) {
    lines.push(`${pad}${INDENT}${quote(status)}: {`);
    lines.push(`${pad}${INDENT}${INDENT}content: ${contentBlock(response.content, depth + 3)};`);
    lines.push(`${pad}${INDENT}};`);
  }
  lines.push(`${pad}};`);
  return `{\n${lines.join('\n')}\n${INDENT.repeat(depth)}}`;
}

const METHODS = ['get', 'put', 'post', 'delete', 'patch'];

/** The full declaration file for an OpenAPI document. */
export function generate(document) {
  const out = [];
  out.push('/**');
  out.push(' * Generated from docs/openapi.json by scripts/openapi-types.mjs.');
  out.push(' * Do not edit: run npm run api:types. src/api/schema.test.ts fails when stale.');
  out.push(` * ${document.info?.title ?? ''} ${document.info?.version ?? ''}`.trimEnd());
  out.push(' */');
  out.push('');
  out.push('export interface paths {');
  for (const [path, item] of Object.entries(document.paths ?? {})) {
    out.push(`${INDENT}${JSON.stringify(path)}: {`);
    for (const method of METHODS) {
      if (item[method]) {
        out.push(`${INDENT}${INDENT}${method}: ${operationType(item[method], item.parameters, 2)};`);
      }
    }
    out.push(`${INDENT}};`);
  }
  out.push('}');
  out.push('');
  out.push('export interface components {');
  out.push(`${INDENT}schemas: {`);
  for (const [name, schema] of Object.entries(document.components?.schemas ?? {})) {
    if (schema.description) {
      out.push(`${INDENT}${INDENT}/** ${schema.description} */`);
    }
    out.push(`${INDENT}${INDENT}${quote(name)}: ${typeOf(schema, 2)};`);
  }
  out.push(`${INDENT}};`);
  out.push('}');
  out.push('');
  out.push('export type operations = {');
  for (const [path, item] of Object.entries(document.paths ?? {})) {
    for (const method of METHODS) {
      const operation = item[method];
      if (operation?.operationId) {
        out.push(
          `${INDENT}${quote(operation.operationId)}: paths[${JSON.stringify(path)}][${JSON.stringify(method)}];`,
        );
      }
    }
  }
  out.push('};');
  out.push('');
  return out.join('\n');
}

function main(argv) {
  const [source, target] = argv;
  if (!source || !target) {
    console.error('usage: openapi-types.mjs <openapi.json> <schema.d.ts>');
    return 2;
  }
  const document = JSON.parse(readFileSync(source, 'utf8'));
  writeFileSync(target, generate(document));
  console.log(`api types: wrote ${target}`);
  return 0;
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  process.exit(main(process.argv.slice(2)));
}
