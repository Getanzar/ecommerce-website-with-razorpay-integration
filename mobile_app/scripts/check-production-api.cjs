const fs = require("node:fs");
const path = require("node:path");

function readEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};

  const env = {};

  for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line || line.startsWith("#")) continue;

    const separator = line.indexOf("=");
    if (separator === -1) continue;

    const key = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    env[key] = value;
  }

  return env;
}

const localEnv = readEnvFile(path.join(process.cwd(), ".env"));

const isEasLifecycleCheck =
  process.env.ZIYAMART_EAS_LIFECYCLE_CHECK === "1";

const isProduction =
  process.env.EXPO_PUBLIC_APP_ENV === "production";

if (isEasLifecycleCheck && !isProduction) {
  console.log("Production API URL check skipped for non-production EAS build.");
  process.exit(0);
}

const apiUrl =
  process.env.EXPO_PUBLIC_API_URL ||
  localEnv.EXPO_PUBLIC_API_URL ||
  "https://ziyamart.in/api/v1";

let parsed;

try {
  parsed = new URL(apiUrl);
} catch {
  console.error(`Invalid production API URL: ${apiUrl}`);
  process.exit(1);
}

const hostname = parsed.hostname.toLowerCase();

const privateHost =
  hostname === "localhost" ||
  hostname === "127.0.0.1" ||
  hostname === "::1" ||
  /^10\./.test(hostname) ||
  /^192\.168\./.test(hostname) ||
  /^172\.(1[6-9]|2\d|3[01])\./.test(hostname);

if (parsed.protocol !== "https:") {
  console.error("Production build blocked: API URL must use HTTPS.");
  console.error(`Current API URL: ${apiUrl}`);
  process.exit(1);
}

if (privateHost) {
  console.error(
    "Production build blocked: API URL cannot use localhost or a private network address.",
  );
  console.error(`Current API URL: ${apiUrl}`);
  process.exit(1);
}

console.log(`Production API URL check passed: ${apiUrl}`);
