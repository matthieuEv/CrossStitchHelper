/**
 * Compact decoding of the grid and progress, mirror of
 * `backend/app/codec.py` — same formats, specification §6.1 and §6.3.
 */

export function base64ToBytes(data: string): Uint8Array {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  // Split into chunks: `String.fromCharCode(...bytes)` exceeds the function
  // call argument limit on a 45,900-cell pattern.
  const chunkSize = 8192;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

/** Decode a little-endian `Uint16Array` layer (§6.3) into a plain JS array. */
export function decodeUint16Layer(data: Uint8Array): Uint16Array {
  // Copy to fix alignment and avoid a `RangeError` if `data.byteOffset` is
  // not a multiple of 2 (happens with a `subarray` slice).
  const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
  return new Uint16Array(buffer);
}

/** Unpack a compact bitmap (1 bit/cell) into one 0/1 byte per cell. */
export function unpackBitmap(bitmap: Uint8Array, cellCount: number): Uint8Array {
  const out = new Uint8Array(cellCount);
  for (let index = 0; index < cellCount; index++) {
    const byteIndex = index >> 3;
    const bitIndex = index & 7;
    const byte = bitmap[byteIndex] ?? 0;
    out[index] = (byte >> bitIndex) & 1;
  }
  return out;
}

/** Pack one 0/1 byte per cell back into a compact bitmap (1 bit/cell). */
export function packBitmap(cells: Uint8Array): Uint8Array {
  const out = new Uint8Array(Math.ceil(cells.length / 8));
  for (let index = 0; index < cells.length; index++) {
    if (!cells[index]) continue;
    const byteIndex = index >> 3;
    const bitIndex = index & 7;
    out[byteIndex] = (out[byteIndex] ?? 0) | (1 << bitIndex);
  }
  return out;
}
