export function assertSafeProductionApiUrl(
  configuredUrl: string,
  isProduction: boolean,
): void {
  if (!isProduction) {
    return;
  }

  let url: URL;

  try {
    url = new URL(configuredUrl);
  } catch {
    throw new Error(
      `Production API URL is invalid: ${configuredUrl}`,
    );
  }

  if (url.protocol !== "https:") {
    throw new Error(
      "Production builds require an HTTPS API URL.",
    );
  }

  const hostname = url.hostname.toLowerCase();

  const isLocalhost =
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1";

  const isPrivateIPv4 =
    /^10\./.test(hostname) ||
    /^192\.168\./.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(hostname);

  if (isLocalhost || isPrivateIPv4) {
    throw new Error(
      "Production builds cannot use a localhost or private-network API URL.",
    );
  }
}
