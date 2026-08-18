/**
 * Direct browser → R2 upload against a presigned PUT URL.
 *
 * XHR rather than `fetch`: upload progress events are the one thing `fetch`
 * still cannot report, and a multi-gigabyte PUT with no progress bar is
 * indistinguishable from a hang.
 */

export interface UploadHandle {
  /** Resolves when R2 has the bytes. */
  done: Promise<void>;
  /** Abort the transfer; `done` rejects with an "upload cancelled" error. */
  cancel(): void;
}

export function putToStorage(
  url: string,
  file: File,
  contentType: string,
  onProgress: (fraction: number) => void,
): UploadHandle {
  const xhr = new XMLHttpRequest();

  const done = new Promise<void>((resolve, reject) => {
    xhr.open("PUT", url);
    // The content type was signed into the URL, so it must be sent verbatim.
    xhr.setRequestHeader("Content-Type", contentType);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () =>
      xhr.status < 300
        ? resolve()
        : reject(new Error(`R2 refused the upload: ${xhr.status} ${xhr.responseText}`));
    xhr.onabort = () => reject(new Error("upload cancelled"));

    // A browser reports DNS failure, TLS failure and a rejected CORS preflight
    // as the same opaque event, so name all three rather than guess. Opening
    // the URL directly tells them apart: DNS/TLS faults fail there too, a CORS
    // fault does not.
    xhr.onerror = () =>
      reject(
        new Error(
          "The upload never left the browser. Either the endpoint host is wrong " +
            "(check R2_ACCOUNT_ID) or the bucket has no CORS policy " +
            `(run scripts/init_r2_cors.py). Host: ${safeHost(url)}`,
        ),
      );

    xhr.send(file);
  });

  return { done, cancel: () => xhr.abort() };
}

function safeHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return "unparseable URL";
  }
}
