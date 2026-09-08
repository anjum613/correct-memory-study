const replacements = new Map([
  [
    'proxy-from-env',
    "export function getProxyForUrl() { return ''; }\n",
  ],
  [
    'form-data',
    "export default class FormData { append() { throw new Error('unused deterministic stub'); } }\n",
  ],
  [
    'follow-redirects',
    "import http from 'node:http'; import https from 'node:https'; export default {http, https};\n",
  ],
]);

export async function resolve(specifier, context, nextResolve) {
  if (replacements.has(specifier)) {
    return {url: `cmpilot-stub:${specifier}`, shortCircuit: true};
  }
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (url.startsWith('cmpilot-stub:')) {
    const specifier = url.slice('cmpilot-stub:'.length);
    return {
      format: 'module',
      source: replacements.get(specifier),
      shortCircuit: true,
    };
  }
  return nextLoad(url, context);
}
