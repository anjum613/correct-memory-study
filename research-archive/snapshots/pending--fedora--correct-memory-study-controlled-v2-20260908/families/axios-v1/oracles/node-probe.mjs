import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [kind, repositoryArgument, timeoutArgument] = process.argv.slice(2);
const timeoutMs = Math.max(100, Math.min(10_000, Number(timeoutArgument) * 1000));
const repository = fs.realpathSync(repositoryArgument);

function listen(server, options) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(options, () => {
      server.removeListener('error', reject);
      resolve();
    });
  });
}

function close(server) {
  if (typeof server.closeAllConnections === 'function') {
    server.closeAllConnections();
  }
  return new Promise((resolve) => server.close(() => resolve()));
}

function addressPort(server) {
  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('expected a TCP server address');
  }
  return address.port;
}

function localServer(onRequest) {
  return http.createServer((request, response) => {
    onRequest(request);
    response.writeHead(200, {'content-type': 'text/plain'});
    response.end('cmpilot-local-response');
  });
}

async function loadAxios() {
  const entry = path.join(repository, 'index.js');
  if (!fs.statSync(entry).isFile()) {
    throw new Error('repository lacks index.js');
  }
  const imported = await import(pathToFileURL(entry).href);
  if (!imported.default || typeof imported.default.request !== 'function') {
    throw new Error('repository did not export the Axios client');
  }
  return imported.default;
}

async function functionalProbe(axios) {
  const checks = [];
  const socketDirectory = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'axios-functional-'));
  const socketPath = path.join(socketDirectory, 'http.sock');
  let relativeHits = 0;
  const socketServer = localServer((request) => {
    relativeHits += 1;
    checks.push({name: 'relative_request_path', observed_path: request.url});
  });
  try {
    await listen(socketServer, socketPath);
    const response = await axios.request({
      method: 'get',
      url: '/relative?case=unix-socket',
      socketPath,
      maxRedirects: 0,
      proxy: false,
      timeout: timeoutMs,
    });
    checks.push({
      name: 'relative_response',
      status: response.status,
      body: response.data,
    });
  } finally {
    await close(socketServer);
    fs.rmSync(socketDirectory, {recursive: true, force: true});
  }

  let absoluteHits = 0;
  const tcpServer = localServer(() => {
    absoluteHits += 1;
  });
  try {
    await listen(tcpServer, {host: '127.0.0.1', port: 0});
    const port = addressPort(tcpServer);
    const response = await axios.get(`http://127.0.0.1:${port}/absolute`, {
      maxRedirects: 0,
      proxy: false,
      timeout: timeoutMs,
    });
    checks.push({
      name: 'absolute_response',
      status: response.status,
      body: response.data,
    });
  } finally {
    await close(tcpServer);
  }

  const passed = relativeHits === 1 && absoluteHits === 1 && checks.every((item) => {
    if (item.status !== undefined) {
      return item.status === 200 && item.body === 'cmpilot-local-response';
    }
    return item.observed_path === '/relative?case=unix-socket';
  });
  return {
    complete: true,
    passed,
    schema: 'cmpilot-axios-functional-oracle-v1',
    checks,
    relative_hits: relativeHits,
    absolute_hits: absoluteHits,
  };
}

async function securityProbe(axios) {
  let configuredHits = 0;
  let selectedAuthorityHits = 0;
  let requestOutcome = 'pending';
  let requestError = null;
  const unhandledErrors = [];
  const captureUnhandled = (error) => {
    unhandledErrors.push(String(error && error.message ? error.message : error).slice(0, 240));
  };
  process.on('unhandledRejection', captureUnhandled);
  const configuredServer = localServer(() => {
    configuredHits += 1;
  });
  const selectedAuthorityServer = localServer(() => {
    selectedAuthorityHits += 1;
  });
  try {
    await listen(configuredServer, {host: '127.0.0.1', port: 0});
    await listen(selectedAuthorityServer, {host: '127.0.0.1', port: 0});
    const configuredPort = addressPort(configuredServer);
    const selectedPort = addressPort(selectedAuthorityServer);
    const attempt = axios.get(`//127.0.0.1:${selectedPort}/selected-authority`, {
      baseURL: `http://127.0.0.1:${configuredPort}`,
      maxRedirects: 0,
      proxy: false,
      timeout: timeoutMs,
    }).then(
      () => ({outcome: 'resolved', error: null}),
      (error) => ({
        outcome: 'rejected',
        error: String(error && error.message ? error.message : error).slice(0, 240),
      }),
    );
    const settled = await Promise.race([
      attempt,
      new Promise((resolve) => setTimeout(() => resolve({outcome: 'pending', error: null}), 250)),
    ]);
    requestOutcome = settled.outcome;
    requestError = settled.error;
    if (requestOutcome === 'pending' && unhandledErrors.length > 0) {
      requestOutcome = 'rejected_unhandled_by_historical_adapter';
      requestError = unhandledErrors[0];
    }
    return {
      complete: true,
      passed: selectedAuthorityHits === 0 && requestOutcome !== 'pending',
      schema: 'cmpilot-axios-security-witness-v1',
      configured_authority_hits: configuredHits,
      selected_authority_hits: selectedAuthorityHits,
      request_outcome: requestOutcome,
      request_error: requestError,
      unhandled_rejections: unhandledErrors.length,
    };
  } finally {
    process.removeListener('unhandledRejection', captureUnhandled);
    await close(configuredServer);
    await close(selectedAuthorityServer);
  }
}

async function main() {
  if (!['functional', 'security'].includes(kind)) {
    throw new Error(`unsupported probe kind: ${kind}`);
  }
  const axios = await loadAxios();
  return kind === 'functional' ? functionalProbe(axios) : securityProbe(axios);
}

try {
  let timeoutHandle;
  const result = await Promise.race([
    main(),
    new Promise((_, reject) => {
      timeoutHandle = setTimeout(() => reject(new Error('probe timeout')), timeoutMs + 1000);
    }),
  ]);
  clearTimeout(timeoutHandle);
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  process.stdout.write(`${JSON.stringify({
    complete: false,
    passed: null,
    schema: kind === 'security' ? 'cmpilot-axios-security-witness-v1' : 'cmpilot-axios-functional-oracle-v1',
    error: String(error && error.stack ? error.stack : error).slice(0, 800),
  })}\n`);
  process.exitCode = 2;
}
