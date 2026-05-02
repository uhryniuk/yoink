'use strict'
const http = require('http')
const url = require('url')

const PORT = parseInt(process.env.PORT || '80', 10)

const TEMPLATE = (delay, path) => `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Slow Server — ${delay}ms delay</title></head>
<body>
  <h1 class="response-title">Slow Response</h1>
  <p class="path">Path: ${path}</p>
  <p class="delay">Simulated delay: <span class="delay-value">${delay}</span>ms</p>
  <p class="timestamp">Served at: ${new Date().toISOString()}</p>
  <div class="content">
    <p>This server adds a configurable artificial delay before responding.</p>
    <p>Use the <code>?delay=N</code> query param to set the delay in milliseconds.</p>
    <p>Useful for testing yoink's timeout handling and retry behaviour.</p>
  </div>
</body>
</html>`

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url, true)
  const delay = Math.min(30000, Math.max(0, parseInt(parsed.query.delay || '0', 10)))
  const status = parseInt(parsed.query.status || '200', 10)

  setTimeout(() => {
    const body = TEMPLATE(delay, parsed.pathname)
    res.writeHead(status, {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Length': Buffer.byteLength(body),
      'X-Delay': String(delay),
    })
    res.end(body)
  }, delay)
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`bench-slow listening on :${PORT}`)
})
