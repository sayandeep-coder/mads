// Minimal static HTTPS server for the Mads Excel task pane. Office add-ins
// must be served over HTTPS even for local development — Excel refuses to
// load a task pane from plain http://, including on localhost. This uses
// the same trusted-locally dev certificate the official Yeoman Office
// generator relies on (via `npm run cert`, which installs it into the
// system/user trust store once), so Excel accepts it without a manual
// "proceed anyway" click.

const fs = require("fs");
const https = require("https");
const path = require("path");
const { getHttpsServerOptions } = require("office-addin-dev-certs");

const PORT = 3000;
const ROOT = __dirname;

const MIME_TYPES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".xml": "application/xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

function serveFile(res, filePath) {
  const ext = path.extname(filePath).toLowerCase();
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("Not found");
      return;
    }
    res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream" });
    res.end(data);
  });
}

async function main() {
  const httpsOptions = await getHttpsServerOptions();

  const server = https.createServer(httpsOptions, (req, res) => {
    const urlPath = req.url.split("?")[0];
    const relative = urlPath === "/" ? "/taskpane.html" : urlPath;
    const filePath = path.join(ROOT, relative);

    // Keep requests inside this folder — no path traversal outside ROOT.
    if (!filePath.startsWith(ROOT)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    serveFile(res, filePath);
  });

  server.listen(PORT, () => {
    console.log(`Mads Excel add-in dev server: https://localhost:${PORT}`);
    console.log(`Manifest: https://localhost:${PORT}/manifest.xml`);
  });
}

main().catch((err) => {
  console.error("Failed to start dev server:", err);
  process.exit(1);
});
