/**
 * server.js · Local standalone server for Snowgate Forum
 */

const http = require('http');
const handler = require('./api/index.js');

const PORT = parseInt(process.env.PORT || '8099', 10);
const HOST = process.env.HOST || '0.0.0.0';

const server = http.createServer((req, res) => {
  handler(req, res);
});

server.listen(PORT, HOST, () => {
  console.log(`[SNOWGATE FORUM] Listening at http://${HOST}:${PORT}/`);
  console.log(`[SNOWGATE FORUM] Ingress domain: forum.snowgate.dev`);
});
