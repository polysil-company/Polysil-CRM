/**
 * Test harness only. Under jsdom the app's `FormData` is jsdom's, while `fetch` (and MSW's
 * request) is Node's, which cannot read a foreign `FormData`: a mock handler that parses an
 * upload waited forever. This encodes the form as multipart bytes first, as a browser does, so
 * `request.formData()` works in mock handlers. Installed after MSW starts, so it runs first.
 */
export function encodeMultipartForTests(): () => void {
  const inner = globalThis.fetch;
  const encoder = new TextEncoder();

  globalThis.fetch = async (input, init) => {
    if (!(init?.body instanceof FormData)) {
      return inner(input, init);
    }
    const boundary = `----polysil-test-${String(Date.now())}`;
    const chunks: Uint8Array[] = [];
    for (const [name, value] of init.body.entries()) {
      if (typeof value === "string") {
        chunks.push(
          encoder.encode(
            `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`,
          ),
        );
      } else {
        chunks.push(
          encoder.encode(
            `--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${value.name}"\r\nContent-Type: ${value.type || "application/octet-stream"}\r\n\r\n`,
          ),
          new Uint8Array(await value.arrayBuffer()),
          encoder.encode("\r\n"),
        );
      }
    }
    chunks.push(encoder.encode(`--${boundary}--\r\n`));
    const body = new Uint8Array(chunks.reduce((size, chunk) => size + chunk.length, 0));
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.length;
    }
    const headers = new Headers(init.headers);
    headers.set("content-type", `multipart/form-data; boundary=${boundary}`);
    return inner(input, { ...init, body, headers });
  };

  return () => {
    globalThis.fetch = inner;
  };
}
