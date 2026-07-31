const http = require('http');
const https = require('https');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
const API_PROXY_PREFIX = '/api-proxy';
const API_TARGET = process.env.MOBILE_API_PROXY_TARGET || 'http://127.0.0.1:8002';

function proxyApiRequest(req, res) {
  const target = new URL(API_TARGET);
  const nextPath = req.url.slice(API_PROXY_PREFIX.length) || '/';
  const requestOptions = {
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port || (target.protocol === 'https:' ? 443 : 80),
    method: req.method,
    path: `${target.pathname.replace(/\/$/, '')}${nextPath}`,
    headers: {
      ...req.headers,
      host: target.host,
    },
  };
  delete requestOptions.headers['content-length'];

  const client = target.protocol === 'https:' ? https : http;
  const proxyReq = client.request(requestOptions, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (error) => {
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ detail: 'api_proxy_failed', message: error.message }));
  });

  req.pipe(proxyReq);
}

const previousEnhanceMiddleware = config.server?.enhanceMiddleware;
config.server = {
  ...config.server,
  enhanceMiddleware(middleware, server) {
    const nextMiddleware = previousEnhanceMiddleware ? previousEnhanceMiddleware(middleware, server) : middleware;
    return (req, res, next) => {
      if (req.url && req.url.startsWith(API_PROXY_PREFIX)) {
        proxyApiRequest(req, res);
        return;
      }
      nextMiddleware(req, res, next);
    };
  },
};

module.exports = config;
