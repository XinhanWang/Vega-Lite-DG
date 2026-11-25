/** Set physical PNG resolution without altering compressed pixels. */
export function pngAt200Dpi(png) {
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (!png.subarray(0, 8).equals(signature)) throw new Error('Expected PNG bytes');
  const physical = Buffer.alloc(21);
  physical.writeUInt32BE(9, 0);
  physical.write('pHYs', 4, 'ascii');
  physical.writeUInt32BE(7874, 8);
  physical.writeUInt32BE(7874, 12);
  physical[16] = 1;
  let crc = 0xffffffff;
  for (const byte of physical.subarray(4, 17)) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  physical.writeUInt32BE((crc ^ 0xffffffff) >>> 0, 17);
  const chunks = [signature];
  let offset = 8;
  let ended = false;
  while (offset < png.length) {
    const size = png.readUInt32BE(offset) + 12;
    if (offset + size > png.length) throw new Error('Truncated PNG chunk');
    const type = png.toString('ascii', offset + 4, offset + 8);
    if (type !== 'pHYs') chunks.push(png.subarray(offset, offset + size));
    if (type === 'IHDR') chunks.push(physical);
    offset += size;
    if (type === 'IEND') { ended = true; break; }
  }
  if (!ended) throw new Error('PNG has no IEND chunk');
  return Buffer.concat(chunks);
}
