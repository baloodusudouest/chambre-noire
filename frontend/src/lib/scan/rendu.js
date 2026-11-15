// Rendu d'une prise, repris tel quel de Scan Immich v3.9 : redressement de perspective (OpenCV), rotation
// écrite dans les pixels, filtres de restauration (grain à graine fixe : même rendu à chaque fois).
// Le rendu reste dans l'iPhone (avis du conseil) : ce que l'on voit est ce qui part.
/* eslint-disable */
function newCanvas(w, h){ const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h)); return c; }
function release(c){ if (c && c.width) { c.width = 0; c.height = 0; } }
function downscale(src, max){
  const f = Math.min(1, max / Math.max(src.width, src.height));
  const c = newCanvas(src.width * f, src.height * f);
  const x = c.getContext('2d'); x.imageSmoothingQuality = 'high'; x.drawImage(src, 0, 0, c.width, c.height);
  return c;
}
function rotateCanvas(src, q){
  q = ((q % 4) + 4) % 4; if (!q) return src;
  const sw = q % 2 === 1;
  const c = newCanvas(sw ? src.height : src.width, sw ? src.width : src.height);
  const x = c.getContext('2d'); x.translate(c.width / 2, c.height / 2); x.rotate(q * Math.PI / 2);
  x.drawImage(src, -src.width / 2, -src.height / 2);
  return c;
}
function toBlob(c, type, q){ return new Promise((res, rej) => c.toBlob(b => b ? res(b) : rej(new Error('Encodage JPEG impossible')), type, q)); }

function warp(cv, src, pts, maxSide){
  const [tl, tr, br, bl] = pts;
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  let w = Math.max(dist(tl, tr), dist(bl, br)), h = Math.max(dist(tl, bl), dist(tr, br));
  const f = Math.min(1, maxSide / Math.max(w, h));
  w = Math.max(16, Math.round(w * f)); h = Math.max(16, Math.round(h * f));
  if (cv) {
    const mats = [];
    try {
      const s = cv.imread(src); mats.push(s);
      const sT = cv.matFromArray(4, 1, cv.CV_32FC2, [tl.x,tl.y, tr.x,tr.y, br.x,br.y, bl.x,bl.y]); mats.push(sT);
      const dT = cv.matFromArray(4, 1, cv.CV_32FC2, [0,0, w,0, w,h, 0,h]); mats.push(dT);
      const T = cv.getPerspectiveTransform(sT, dT); mats.push(T);
      const d = new cv.Mat(); mats.push(d);
      cv.warpPerspective(s, d, T, new cv.Size(w, h), cv.INTER_LINEAR, cv.BORDER_REPLICATE, new cv.Scalar());
      const out = newCanvas(w, h); cv.imshow(out, d);
      return out;
    } catch(e){ console.warn('Warp', e); }
    finally { mats.forEach(m => { try { m.delete(); } catch(e){} }); }
  }
  // repli sans OpenCV : recadrage rectangulaire englobant
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const x0 = Math.max(0, Math.min(...xs)), y0 = Math.max(0, Math.min(...ys));
  const x1 = Math.min(src.width, Math.max(...xs)), y1 = Math.min(src.height, Math.max(...ys));
  const bw = x1 - x0, bh = y1 - y0, g = Math.min(1, maxSide / Math.max(bw, bh));
  const out = newCanvas(bw * g, bh * g);
  const x = out.getContext('2d'); x.imageSmoothingQuality = 'high';
  x.drawImage(src, x0, y0, bw, bh, 0, 0, out.width, out.height);
  return out;
}

function applyFilter(src, name, intensity){
  if (name === 'none' || intensity <= 0) return src;
  const w = src.width, h = src.height;
  const out = newCanvas(w, h);
  const ctx = out.getContext('2d', {willReadFrequently:true});
  ctx.drawImage(src, 0, 0);
  const img = ctx.getImageData(0, 0, w, h), d = img.data, k = Math.min(1, intensity / 100);
  // grain pseudo-aléatoire à graine fixe : un nouvel envoi produit exactement les mêmes octets
  let seed = 0x2545F491 ^ (w * 73856093) ^ (h * 19349663);
  const rnd = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed >>> 0) / 4294967296; };

  // niveaux automatiques par canal (corrige la dérive de couleur des tirages passés)
  const hist = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)]; let cnt = 0;
  for (let i = 0; i < d.length; i += 16) { hist[0][d[i]]++; hist[1][d[i+1]]++; hist[2][d[i+2]]++; cnt++; }
  const pct = (hh, p) => { let a = 0; const t = cnt * p; for (let v = 0; v < 256; v++) { a += hh[v]; if (a >= t) return v; } return 255; };
  const luts = [0, 1, 2].map(c => {
    let lo = pct(hist[c], 0.005), hi = pct(hist[c], 0.995);
    if (hi - lo < 24) { lo = 0; hi = 255; }
    const L = new Float32Array(256);
    for (let v = 0; v < 256; v++) L[v] = Math.max(0, Math.min(255, (v - lo) * 255 / (hi - lo)));
    return L;
  });

  // courbe tonale
  const P = {
    restore:   {contrast:0.15, lift:0.00, roll:1.00, sat:1.12, grain:0,  vig:0,    stretch:1.0},
    authentic: {contrast:0.30, lift:0.07, roll:0.90, sat:0.80, grain:9,  vig:0.28, stretch:0.6},
    bw:        {contrast:0.45, lift:0.03, roll:0.96, sat:0,    grain:7,  vig:0.20, stretch:1.0},
    sepia:     {contrast:0.30, lift:0.05, roll:0.93, sat:0,    grain:6,  vig:0.22, stretch:1.0}
  }[name];
  const curve = new Float32Array(256);
  for (let v = 0; v < 256; v++) {
    const x = v / 255, s = x * x * (3 - 2 * x);
    const y = x + (s - x) * P.contrast;
    curve[v] = (P.lift + y * (P.roll - P.lift)) * 255;
  }
  const c255 = n => n < 0 ? 0 : n > 255 ? 255 : n | 0;
  const cx = w / 2, cy = h / 2, maxd2 = cx * cx + cy * cy;

  for (let y = 0; y < h; y++) {
    const dy2 = (y - cy) * (y - cy);
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      const r0 = d[i], g0 = d[i+1], b0 = d[i+2];
      let r = r0 + (luts[0][r0] - r0) * P.stretch;
      let g = g0 + (luts[1][g0] - g0) * P.stretch;
      let b = b0 + (luts[2][b0] - b0) * P.stretch;
      const l = 0.299 * r + 0.587 * g + 0.114 * b;
      if (name === 'restore' || name === 'authentic') {
        r = curve[c255(l + (r - l) * P.sat)];
        g = curve[c255(l + (g - l) * P.sat)];
        b = curve[c255(l + (b - l) * P.sat)];
        if (name === 'authentic') { r = r * 1.05 + 4; g = g * 1.0 + 2; b = b * 0.90; }
      } else {
        const v = curve[c255(l)];
        if (name === 'bw') { r = v + 3; g = v; b = v - 3; }
        else { const t = (v / 255) * (1 - v / 255) * 4; r = v + 30 * t + 6; g = v + 10 * t; b = v - 24 * t; }
      }
      if (P.vig) {
        const f = 1 - P.vig * Math.pow(((x - cx) * (x - cx) + dy2) / maxd2, 1.3);
        r *= f; g *= f; b *= f;
      }
      if (P.grain) {
        const n = (rnd() + rnd() - 1) * P.grain;
        r += n; g += n; b += n;
      }
      d[i]   = r0 + (r - r0) * k;
      d[i+1] = g0 + (g - g0) * k;
      d[i+2] = b0 + (b - b0) * k;
    }
  }
  ctx.putImageData(img, 0, 0);
  return out;
}



export { newCanvas, release, downscale, rotateCanvas, toBlob, warp, applyFilter }
