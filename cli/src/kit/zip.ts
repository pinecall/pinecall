/** A zip archive read whole in memory: each file's path and bytes, stored or deflated, none outside the folder it is read into. */

import { inflateRawSync } from "node:zlib";

import { PinecallError } from "../errors.js";

/** One file of an archive: its path inside it, `/`-separated, and its bytes. */
export interface ZipEntry {
  path: string;
  data: Buffer;
}

const END_OF_DIRECTORY = 0x06054b50;
const DIRECTORY_ENTRY = 0x02014b50;
const LOCAL_HEADER = 0x04034b50;
const END_LENGTH = 22;
const LONGEST_COMMENT = 0xffff;
const STORED = 0;
const DEFLATED = 8;

export const NOT_A_ZIP = "the answer is not a zip archive";

/** Every file of the archive, read by its central directory; folders left out. */
export function unzip(bytes: Uint8Array): ZipEntry[] {
  const zip = Buffer.from(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const end = endOfDirectory(zip);
  const count = zip.readUInt16LE(end + 10);
  let at = zip.readUInt32LE(end + 16);
  const found: ZipEntry[] = [];
  for (let read = 0; read < count; read += 1) {
    if (zip.readUInt32LE(at) !== DIRECTORY_ENTRY) throw new PinecallError(NOT_A_ZIP);
    const method = zip.readUInt16LE(at + 10);
    const packed = zip.readUInt32LE(at + 20);
    const size = zip.readUInt32LE(at + 24);
    const nameLength = zip.readUInt16LE(at + 28);
    const local = zip.readUInt32LE(at + 42);
    const path = zip.toString("utf8", at + 46, at + 46 + nameLength);
    at += 46 + nameLength + zip.readUInt16LE(at + 30) + zip.readUInt16LE(at + 32);
    if (path.endsWith("/")) continue;
    // The local header's own name and extra may differ in length from the directory's: its data starts after them.
    if (zip.readUInt32LE(local) !== LOCAL_HEADER) throw new PinecallError(NOT_A_ZIP);
    const start = local + 30 + zip.readUInt16LE(local + 26) + zip.readUInt16LE(local + 28);
    const data = contentOf(zip.subarray(start, start + packed), method, path);
    if (data.length !== size) throw new PinecallError(`${path} in the archive is not the size its directory says`);
    found.push({ path: inside(path), data });
  }
  return found;
}

function endOfDirectory(zip: Buffer): number {
  // The record is the last 22 bytes, unless a comment follows it.
  for (let at = zip.length - END_LENGTH; at >= Math.max(0, zip.length - END_LENGTH - LONGEST_COMMENT); at -= 1) {
    if (zip.readUInt32LE(at) === END_OF_DIRECTORY) return at;
  }
  throw new PinecallError(NOT_A_ZIP);
}

function contentOf(raw: Buffer, method: number, path: string): Buffer {
  if (method === STORED) return Buffer.from(raw);
  if (method === DEFLATED) return inflateRawSync(raw);
  throw new PinecallError(`${path} in the archive is packed in a way this CLI does not read (method ${method})`);
}

/** A path that stays inside the folder: none absolute, none climbing out with `..`. */
function inside(path: string): string {
  if (path.startsWith("/") || path.includes("\\") || /^[A-Za-z]:/.test(path) || path.split("/").includes("..")) {
    throw new PinecallError(`the archive names ${path}, outside the folder it is read into`);
  }
  return path;
}
