// Détection du tirage, reprise TELLE QUELLE de Scan Immich v3.9 (code éprouvé sur fonds blancs avec ombres,
// cuir bordeaux, cuir bleu texturé, feuille posée sur une table, pages d'album). Ne pas « améliorer » sans
// repasser le banc d'images (tests/images) : chaque seuil corrige un fond qui a échoué.
// Entrée : un cv.Mat RGBA (image réduite à ~420 px de grand côté). Sortie : {pts:[tl,tr,br,bl], fill, area, uniform}
// en coordonnées du Mat, ou null ; avec multi=true : {prints:[…]} (1 à 4 tirages, ordre de lecture).
/* eslint-disable */
function findPrint(cv, rgba, multi){
  const W = rgba.cols, H = rgba.rows, area = W * H;
  const mats = []; const M = m => { mats.push(m); return m; };
  try {
    const rgb = M(new cv.Mat()); cv.cvtColor(rgba, rgb, cv.COLOR_RGBA2RGB);
    cv.GaussianBlur(rgb, rgb, new cv.Size(5, 5), 0);
    const lab = M(new cv.Mat()); cv.cvtColor(rgb, lab, cv.COLOR_RGB2Lab);
    const d = lab.data;

    // 1) modèle du fond à partir d'une bande en bordure (6 %) :
    //    a) couleur médiane globale, b) plan ajusté (x, y) qui suit un dégradé d'éclairage
    const bw = Math.max(4, Math.round(Math.min(W, H) * 0.06));
    const S = [];
    for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2) {
      if (x >= bw && x < W - bw && y >= bw && y < H - bw) continue;
      const i = (y * W + x) * 3; S.push([x, y, d[i], d[i + 1], d[i + 2]]);
    }
    const med = a => { a.sort((p, q) => p - q); return a[a.length >> 1]; };
    const global = [2, 3, 4].map(c => { const m0 = med(S.map(v => v[c])); return [m0, 0, 0]; });
    const fitPlane = (pts, c) => {          // moindres carrés v = k0 + k1·x + k2·y
      let n = 0, sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0, sv = 0, sxv = 0, syv = 0;
      for (const p of pts) { const x = p[0], y = p[1], v = p[c]; n++; sx += x; sy += y; sxx += x * x; sxy += x * y; syy += y * y; sv += v; sxv += x * v; syv += y * v; }
      const A = [[n, sx, sy], [sx, sxx, sxy], [sy, sxy, syy]], B = [sv, sxv, syv];
      const det3 = m => m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
      const D = det3(A); if (Math.abs(D) < 1e-9) return [sv / Math.max(1, n), 0, 0];
      return [0, 1, 2].map(k => det3(A.map((row, r) => row.map((v, cc) => cc === k ? B[r] : v))) / D);
    };
    let plane = [2, 3, 4].map(c => fitPlane(S, c));
    {   // deuxième passe sans les points aberrants (ombres, objets en bordure)
      const res = S.map(p => Math.hypot(...[2, 3, 4].map((c, k) => p[c] - (plane[k][0] + plane[k][1] * p[0] + plane[k][2] * p[1]))));
      const mr = med(res.slice()), keep = S.filter((p, i) => res[i] <= mr * 2.5 + 2);
      if (keep.length > 30) plane = [2, 3, 4].map(c => fitPlane(keep, c));
    }

    const short = Math.min(W, H), odd = v => (v | 1);
    // page d'album : fermeture plus petite pour ne pas souder deux tirages proches
    const ko = odd(Math.max(3, Math.round(short * 0.014))), kc = odd(Math.max(5, Math.round(short * (multi ? 0.015 : 0.03))));
    const kOpen = M(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(ko, ko)));
    const kClose = M(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(kc, kc)));
    const dist = M(new cv.Mat(H, W, cv.CV_8UC1)); const dd = dist.data;
    const otsuTmp = M(new cv.Mat());
    const mask = M(new cv.Mat());
    let uniform = false;

    const margin = Math.max(3, Math.round(Math.min(W, H) * 0.012));
    // plus grand contour quasi rectangulaire, évalué sur son enveloppe convexe
    // (tolère les zones du tirage proches du fond, ex. ciel clair sur fond blanc)
    const pick = (bin, minFill) => {
      const contours = new cv.MatVector(), hier = new cv.Mat();
      cv.findContours(bin, contours, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      let best = null; const all = [];
      for (let i = 0; i < contours.size(); i++) {
        const c = contours.get(i);
        const a = Math.abs(cv.contourArea(c));
        if (a > area * (multi ? 0.02 : 0.04) && a < area * 0.95) {
          const br = cv.boundingRect(c);
          const touches = br.x <= margin || br.y <= margin || br.x + br.width >= W - margin || br.y + br.height >= H - margin;
          const hull = new cv.Mat(); cv.convexHull(c, hull, false, true);
          const ha = Math.abs(cv.contourArea(hull));
          const r = cv.minAreaRect(hull);
          const ra = r.size.width * r.size.height;
          const fill = ra > 0 ? ha / ra : 0, solidity = ha > 0 ? a / ha : 0;
          if (!touches && fill > minFill && solidity > 0.55 && ha < area * 0.95) {
            const pts = quadFromHull(hull, r) || cv.RotatedRect.points(r).map(p => ({x:p.x, y:p.y}));
            const score = ha * fill * (0.5 + 0.5 * solidity);
            const cand = {pts, score, fill, area:ha / area};
            all.push(cand);
            if (!best || score > best.score) best = cand;
          }
          hull.delete();
        }
        c.delete();
      }
      contours.delete(); hier.delete();
      return {best, all};
    };

    let best = null, bestList = null, bestListScore = 0;
    // 2) carte de distance au fond (chrominance plus forte que la luminance), pour chaque modèle
    for (const [model, wl] of [[global, 0.6], [plane, 0.45]]) {
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const p = y * W + x, i = p * 3;
        const bL = model[0][0] + model[0][1] * x + model[0][2] * y;
        const bA = model[1][0] + model[1][1] * x + model[1][2] * y;
        const bB = model[2][0] + model[2][1] * x + model[2][2] * y;
        const dl = (d[i] - bL) * wl, da = d[i + 1] - bA, db = d[i + 2] - bB;
        dd[p] = Math.min(255, Math.sqrt(dl * dl + da * da + db * db) * 2);
      }
      // 3) seuils candidats : robuste (médiane + écart médian de la bordure), Otsu, plus bas
      const bvals = [];
      for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2)
        if (x < bw || x >= W - bw || y < bw || y >= H - bw) bvals.push(dd[y * W + x]);
      const bMed = med(bvals.slice()), bMad = med(bvals.map(v => Math.abs(v - bMed)));
      if (bMad < 6) uniform = true;
      const otsu = cv.threshold(dist, otsuTmp, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
      const robust = bMed + 4 * bMad + 12;
      const thresholds = [...new Set([robust, otsu, (robust + otsu) / 2, bMed + 2.5 * bMad + 8, 55, 40]
        .map(t => Math.round(Math.max(22, Math.min(110, t)))))];
      for (const t of thresholds) {
        cv.threshold(dist, mask, t, 255, cv.THRESH_BINARY);
        cv.morphologyEx(mask, mask, cv.MORPH_OPEN, kOpen);
        cv.morphologyEx(mask, mask, cv.MORPH_CLOSE, kClose);
        const {best:b, all} = pick(mask, 0.88);
        if (b && (!best || b.score > best.score)) best = b;
        if (multi && all.length) {        // page d'album : le meilleur ensemble de tirages (score total)
          const tot = all.reduce((p, c) => p + c.score, 0);
          if (tot > bestListScore) { bestListScore = tot; bestList = all.slice(0, 6); }
        }
      }
    }

    // repli : contours (fonds texturés ou peu contrastés)
    if (!best) {
      const gray = M(new cv.Mat()); cv.cvtColor(rgb, gray, cv.COLOR_RGB2GRAY);
      const edges = M(new cv.Mat()); cv.Canny(gray, edges, 30, 100);
      const k5 = M(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5)));
      cv.dilate(edges, edges, k5);
      cv.morphologyEx(edges, edges, cv.MORPH_CLOSE, kClose);
      // remplit l'intérieur des contours fermés
      const filled = M(cv.Mat.zeros(H, W, cv.CV_8UC1));
      const cs = new cv.MatVector(), hh = new cv.Mat();
      cv.findContours(edges, cs, hh, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
      cv.drawContours(filled, cs, -1, new cv.Scalar(255), -1);
      cs.delete(); hh.delete();
      cv.morphologyEx(filled, filled, cv.MORPH_OPEN, kOpen);
      best = pick(filled, 0.88).best;
    }
    // les bords rectilignes priment si la couleur n'a rien donné de net
    if (!best || best.fill < 0.93) {
      const lb = findPrintLines(cv, rgba);
      if (lb && (!best || lb.area > best.area * 0.8)) best = {pts:lb.pts, score:lb.score, fill:Math.max(0.9, lb.fill), area:lb.area};
    }
    if (multi) {
      let list = bestList && bestList.length ? bestList : (best ? [best] : []);
      list = list.sort((p, q) => q.score - p.score).slice(0, 4).map(c => Object.assign({}, c, {pts: orderPts(c.pts)}));
      // ordre de lecture : rangées de haut en bas, puis de gauche à droite
      const ctr = c => ({x: c.pts.reduce((a, p) => a + p.x, 0) / 4, y: c.pts.reduce((a, p) => a + p.y, 0) / 4});
      list.sort((p, q) => { const a = ctr(p), b = ctr(q); return Math.abs(a.y - b.y) > H * 0.12 ? a.y - b.y : a.x - b.x; });
      return {prints: list};
    }
    if (!best) return null;
    return {pts: orderPts(best.pts), score: best.score, fill: best.fill, area: best.area, uniform};
  } catch(e){ console.warn('Détection', e); return null; }
  finally { mats.forEach(m => { try { m.delete(); } catch(e){} }); }
}

/* Tirage posé sur une feuille ou un carton clair : la première détection trouve la feuille
   (plus grand objet distinct de la table). On cherche alors un tirage À L'INTÉRIEUR, avec la
   feuille comme fond. Accepté seulement si la feuille est uniforme et laisse une vraie marge
   (≥ 7 % de chaque côté, tirage ≤ 68 % de la surface) : une bordure blanche de tirage, plus
   fine, est conservée. */
function findPrintNested(cv, rgba){
  const r = findPrint(cv, rgba);
  if (!r || r.fill < 0.88) return r;
  const W = rgba.cols, H = rgba.rows;
  const xs = r.pts.map(p => p.x), ys = r.pts.map(p => p.y);
  // rectangle englobant de la feuille, réduit de 3 % pour exclure son bord et la table
  const bw0 = Math.max(...xs) - Math.min(...xs), bh0 = Math.max(...ys) - Math.min(...ys);
  const x0 = Math.max(0, Math.round(Math.min(...xs) + bw0 * 0.03)), y0 = Math.max(0, Math.round(Math.min(...ys) + bh0 * 0.03));
  const x1 = Math.min(W, Math.round(Math.max(...xs) - bw0 * 0.03)), y1 = Math.min(H, Math.round(Math.max(...ys) - bh0 * 0.03));
  const rw = x1 - x0, rh = y1 - y0;
  if (rw < 60 || rh < 60) return r;
  let sub = null, inner = null;
  try {
    sub = rgba.roi(new cv.Rect(x0, y0, rw, rh)).clone();
    inner = findPrint(cv, sub);
  } catch(e){ inner = null; }
  finally { if (sub) sub.delete(); }
  if (!inner || inner.fill < 0.9 || !inner.uniform || inner.area > 0.68 || inner.area < 0.12) return r;
  const ix = inner.pts.map(p => p.x), iy = inner.pts.map(p => p.y);
  const mL = Math.min(...ix) / rw, mR = 1 - Math.max(...ix) / rw, mT = Math.min(...iy) / rh, mB = 1 - Math.max(...iy) / rh;
  if (Math.min(mL, mR, mT, mB) < 0.07) return r;
  return Object.assign({}, inner, {pts: inner.pts.map(p => ({x:p.x + x0, y:p.y + y0})), area: inner.area * rw * rh / (W * H), nested:true});
}

/* Quadrilatère à partir de l'enveloppe convexe : chaque côté du tirage est une droite
   ajustée sur les segments de l'enveloppe parallèles à ce côté. Les coins « rognés »
   (zone du tirage proche du fond) sont reconstruits par intersection des droites,
   et la perspective est conservée. */
function quadFromHull(hull, rect){
  const n = hull.rows; if (n < 4) return null;
  const P = []; for (let i = 0; i < n; i++) P.push({x:hull.data32S[i * 2], y:hull.data32S[i * 2 + 1]});
  const th = rect.angle * Math.PI / 180, ux = Math.cos(th), uy = Math.sin(th), vx = -uy, vy = ux;
  const cx = rect.center.x, cy = rect.center.y;
  const groups = [[], [], [], []];   // côtés : 0 et 2 parallèles à u, 1 et 3 parallèles à v
  for (let i = 0; i < n; i++) {
    const a = P[i], b = P[(i + 1) % n];
    const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy); if (L < 2) continue;
    const cu = Math.abs((dx * ux + dy * uy) / L), cvv = Math.abs((dx * vx + dy * vy) / L);
    const mx = (a.x + b.x) / 2 - cx, my = (a.y + b.y) / 2 - cy;
    if (cu > 0.94) groups[(mx * vx + my * vy) < 0 ? 0 : 2].push({a, b, L});
    else if (cvv > 0.94) groups[(mx * ux + my * uy) < 0 ? 3 : 1].push({a, b, L});
  }
  if (groups.some(g => !g.length)) return null;
  const lines = groups.map(g => {
    let sx = 0, sy = 0, sw = 0, dxs = 0, dys = 0;
    const ref = {x:g[0].b.x - g[0].a.x, y:g[0].b.y - g[0].a.y};
    for (const e of g) {
      sx += (e.a.x + e.b.x) / 2 * e.L; sy += (e.a.y + e.b.y) / 2 * e.L; sw += e.L;
      let ex = e.b.x - e.a.x, ey = e.b.y - e.a.y; if (ex * ref.x + ey * ref.y < 0) { ex = -ex; ey = -ey; }
      dxs += ex; dys += ey;
    }
    const dl = Math.hypot(dxs, dys);
    return {px:sx / sw, py:sy / sw, dx:dxs / dl, dy:dys / dl};
  });
  const inter = (l1, l2) => {
    const den = l1.dx * l2.dy - l1.dy * l2.dx; if (Math.abs(den) < 1e-6) return null;
    const t = ((l2.px - l1.px) * l2.dy - (l2.py - l1.py) * l2.dx) / den;
    return {x:l1.px + t * l1.dx, y:l1.py + t * l1.dy};
  };
  const q = [inter(lines[3], lines[0]), inter(lines[0], lines[1]), inter(lines[1], lines[2]), inter(lines[2], lines[3])];
  if (q.some(p => !p)) return null;
  // garde-fou : le quadrilatère doit rester proche du rectangle englobant
  const diag = Math.hypot(rect.size.width, rect.size.height);
  if (q.some(p => Math.hypot(p.x - cx, p.y - cy) > diag * 0.75)) return null;
  return q;
}

/* Détection par les bords rectilignes du tirage (fonds texturés / éclairage inégal) :
   segments longs (Hough) → 2 droites « horizontales » + 2 « verticales » →
   quadrilatère le plus grand dont les 4 côtés suivent bien des bords réels. */
function findPrintLines(cv, rgba){
  const W = rgba.cols, H = rgba.rows, area = W * H, short = Math.min(W, H);
  const mats = []; const M = m => { mats.push(m); return m; };
  try {
    const gray = M(new cv.Mat()); cv.cvtColor(rgba, gray, cv.COLOR_RGBA2GRAY);
    cv.GaussianBlur(gray, gray, new cv.Size(5, 5), 0);
    const edges = M(new cv.Mat()); cv.Canny(gray, edges, 30, 90);
    const lines = M(new cv.Mat());
    cv.HoughLinesP(edges, lines, 1, Math.PI / 180, Math.round(short * 0.12), Math.round(short * 0.22), Math.round(short * 0.03));
    const segs = [];
    for (let i = 0; i < lines.rows; i++) {
      const [x1, y1, x2, y2] = lines.data32S.slice(i * 4, i * 4 + 4);
      const L = Math.hypot(x2 - x1, y2 - y1); let a = Math.atan2(y2 - y1, x2 - x1); if (a < 0) a += Math.PI;
      segs.push({x1, y1, x2, y2, L, a});
    }
    if (segs.length < 4) return null;
    const ed = M(new cv.Mat()); cv.dilate(edges, ed, M(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5))));
    const E = ed.data;
    // droites infinies : point + direction ; regroupement horizontal / vertical (±30°)
    const toLine = s => ({px:(s.x1 + s.x2) / 2, py:(s.y1 + s.y2) / 2, dx:Math.cos(s.a), dy:Math.sin(s.a), L:s.L, a:s.a});
    const hor = segs.filter(s => s.a < Math.PI / 6 || s.a > Math.PI * 5 / 6).map(toLine).sort((p, q) => q.L - p.L).slice(0, 10);
    const ver = segs.filter(s => Math.abs(s.a - Math.PI / 2) < Math.PI / 6).map(toLine).sort((p, q) => q.L - p.L).slice(0, 10);
    if (hor.length < 2 || ver.length < 2) return null;
    const inter = (l1, l2) => {
      const den = l1.dx * l2.dy - l1.dy * l2.dx; if (Math.abs(den) < 1e-6) return null;
      const t = ((l2.px - l1.px) * l2.dy - (l2.py - l1.py) * l2.dx) / den;
      return {x:l1.px + t * l1.dx, y:l1.py + t * l1.dy};
    };
    const support = (a, b) => {   // part des points du côté [a,b] posés sur un bord
      const n = Math.max(12, Math.round(Math.hypot(b.x - a.x, b.y - a.y) / 3)); let hit = 0;
      for (let k = 0; k <= n; k++) {
        const x = Math.round(a.x + (b.x - a.x) * k / n), y = Math.round(a.y + (b.y - a.y) * k / n);
        if (x >= 0 && y >= 0 && x < W && y < H && E[y * W + x]) hit++;
      }
      return hit / (n + 1);
    };
    const margin = Math.max(3, Math.round(short * 0.012));
    let best = null;
    for (let i = 0; i < hor.length; i++) for (let j = i + 1; j < hor.length; j++) {
      let t = hor[i], b = hor[j]; if (t.py > b.py) [t, b] = [b, t];
      if (b.py - t.py < short * 0.15) continue;
      for (let k = 0; k < ver.length; k++) for (let l = k + 1; l < ver.length; l++) {
        let lf = ver[k], rt = ver[l]; if (lf.px > rt.px) [lf, rt] = [rt, lf];
        if (rt.px - lf.px < short * 0.15) continue;
        const q = [inter(t, lf), inter(t, rt), inter(b, rt), inter(b, lf)];
        if (q.some(p => !p || p.x < margin || p.y < margin || p.x > W - margin || p.y > H - margin)) continue;
        let qa = 0; for (let m = 0; m < 4; m++) { const p = q[m], r = q[(m + 1) % 4]; qa += p.x * r.y - r.x * p.y; } qa = Math.abs(qa) / 2;
        if (qa < area * 0.05 || qa > area * 0.9) continue;
        const sup = [0, 1, 2, 3].map(m => support(q[m], q[(m + 1) % 4]));
        const minS = Math.min(...sup), avgS = sup.reduce((p, c) => p + c, 0) / 4;
        if (minS < 0.45 || avgS < 0.65) continue;
        const score = qa * avgS;
        if (!best || score > best.score) best = {pts:q, score, fill:avgS, area:qa / area};
      }
    }
    return best;
  } catch(e){ console.warn('Détection (bords)', e); return null; }
  finally { mats.forEach(m => { try { m.delete(); } catch(e){} }); }
}
// DETECT-END
function orderPts(p){
  const cx = p.reduce((a, q) => a + q.x, 0) / 4, cy = p.reduce((a, q) => a + q.y, 0) / 4;
  const s = p.slice().sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
  let k = 0; for (let i = 1; i < 4; i++) if (s[i].x + s[i].y < s[k].x + s[k].y) k = i;
  return [s[k], s[(k + 1) % 4], s[(k + 2) % 4], s[(k + 3) % 4]];
}

export { findPrint, findPrintNested, quadFromHull, findPrintLines, orderPts }
