/**
 * Décodage compact de la grille et de la progression, miroir de
 * `backend/app/codec.py` — mêmes formats, cahier des charges §6.1 et §6.3.
 */

export function base64ToBytes(data: string): Uint8Array {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  // Découpé par blocs : `String.fromCharCode(...bytes)` dépasse la limite
  // d'arguments d'un appel de fonction sur un motif de 45 900 cases.
  const chunkSize = 8192;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

/** Décode une couche `Uint16Array` little-endian (§6.3) en tableau JS classique. */
export function decodeUint16Layer(data: Uint8Array): Uint16Array {
  // Copie l'alignement pour éviter un `RangeError` si `data.byteOffset` n'est
  // pas multiple de 2 (arrive avec un sous-tableau issu de `subarray`).
  const buffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
  return new Uint16Array(buffer);
}

/** Déballe un bitmap compact (1 bit/case) en un octet 0/1 par case. */
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

/** Remballe un octet 0/1 par case en bitmap compact (1 bit/case). */
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
