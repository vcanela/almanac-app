// Almanac astronomy: where the Sun, Moon, planets and stars are in the sky.
//
// Low-precision methods, good to a small fraction of a degree for 1800 to 2050,
// far finer than the sky chart can show:
//   Planets: Keplerian elements and rates from E. M. Standish, "Approximate
//     Positions of the Planets" (JPL), Table 1, in the J2000 ecliptic frame.
//   Moon: Paul Schlyter's method ("How to compute planetary positions"), with
//     the main perturbation terms, in the frame of date; topocentric parallax.
//   Precession J2000 to date: Meeus, Astronomical Algorithms, 21.2.
//   Sidereal time: Meeus 12.4.
// Ignored as too small to see: nutation, aberration, light time, Delta T.
// Angles are in degrees unless a name says otherwise.

(function () {
  'use strict';
  const RAD = Math.PI / 180;
  const sin = d => Math.sin(d * RAD), cos = d => Math.cos(d * RAD);
  const atan2 = (y, x) => Math.atan2(y, x) / RAD, asin = x => Math.asin(Math.max(-1, Math.min(1, x))) / RAD;
  const norm = d => ((d % 360) + 360) % 360;

  const julian = date => date.getTime() / 86400000 + 2440587.5;

  // Elements at J2000 and their rates per Julian century:
  // a (au), e, I, L (mean longitude), varpi (longitude of perihelion), Omega (node).
  const ELEMENTS = {
    mercury: [0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593,
              0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081],
    venus:   [0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255,
              0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418],
    earth:   [1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0,
              0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0],
    mars:    [1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891,
              0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343],
    jupiter: [5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909,
              -0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106],
    saturn:  [9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448,
              -0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794],
  };

  function kepler(M, e) {
    // Solve E - e sin E = M (degrees), Newton iteration.
    let E = M + (e / RAD) * sin(M);
    for (let k = 0; k < 8; k++) {
      const dE = (M - (E - (e / RAD) * sin(E))) / (1 - e * cos(E));
      E += dE;
      if (Math.abs(dE) < 1e-7) break;
    }
    return E;
  }

  // Heliocentric J2000 ecliptic position (au).
  function heliocentric(name, T) {
    const el = ELEMENTS[name];
    const [a, e, I, L, wbar, node] = el.slice(0, 6).map((v, i) => v + el[i + 6] * T);
    const w = wbar - node;
    const M = norm(L - wbar + 180) - 180;
    const E = kepler(M, e);
    const xp = a * (cos(E) - e), yp = a * Math.sqrt(1 - e * e) * sin(E);
    return [
      (cos(w) * cos(node) - sin(w) * sin(node) * cos(I)) * xp + (-sin(w) * cos(node) - cos(w) * sin(node) * cos(I)) * yp,
      (cos(w) * sin(node) + sin(w) * cos(node) * cos(I)) * xp + (-sin(w) * sin(node) + cos(w) * cos(node) * cos(I)) * yp,
      sin(w) * sin(I) * xp + cos(w) * sin(I) * yp,
    ];
  }

  // Ecliptic rectangular to equatorial RA/Dec, for a given obliquity.
  function eclipticToEquatorial([x, y, z], eps) {
    const ye = y * cos(eps) - z * sin(eps), ze = y * sin(eps) + z * cos(eps);
    return { ra: norm(atan2(ye, x)), dec: atan2(ze, Math.hypot(x, ye)), dist: Math.hypot(x, y, z) };
  }

  // Precession of J2000 RA/Dec to the mean equinox of date (Meeus 21.2).
  function precess(ra, dec, T) {
    const s = 1 / 3600;
    const zeta = (2306.2181 * T + 0.30188 * T * T + 0.017998 * T ** 3) * s;
    const z = (2306.2181 * T + 1.09468 * T * T + 0.018203 * T ** 3) * s;
    const th = (2004.3109 * T - 0.42665 * T * T - 0.041833 * T ** 3) * s;
    const A = cos(dec) * sin(ra + zeta);
    const B = cos(th) * cos(dec) * cos(ra + zeta) - sin(th) * sin(dec);
    const C = sin(th) * cos(dec) * cos(ra + zeta) + cos(th) * sin(dec);
    return { ra: norm(atan2(A, B) + z), dec: asin(C) };
  }

  // Greenwich mean sidereal time (Meeus 12.4).
  function gmst(jd) {
    const T = (jd - 2451545) / 36525;
    return norm(280.46061837 + 360.98564736629 * (jd - 2451545) + 0.000387933 * T * T - T ** 3 / 38710000);
  }

  // The Sun and planets: apparent geocentric RA/Dec of date (no aberration or nutation).
  function planet(name, jd) {
    const T = (jd - 2451545) / 36525;
    const earth = heliocentric('earth', T);
    const p = name === 'sun' ? [0, 0, 0] : heliocentric(name, T);
    const geo = [p[0] - earth[0], p[1] - earth[1], p[2] - earth[2]];
    const eq = eclipticToEquatorial(geo, 23.43928);
    return { ...precess(eq.ra, eq.dec, T), dist: eq.dist };
  }

  // The Moon: geocentric RA/Dec of date, distance in Earth radii, ecliptic longitude.
  function moon(jd) {
    const d = jd - 2451543.5;
    const N = norm(125.1228 - 0.0529538083 * d), i = 5.1454, w = norm(318.0634 + 0.1643573223 * d);
    const a = 60.2666, e = 0.0549, M = norm(115.3654 + 13.0649929509 * d);
    const E = kepler(M, e);
    const xv = a * (cos(E) - e), yv = a * Math.sqrt(1 - e * e) * sin(E);
    const v = atan2(yv, xv);
    let r = Math.hypot(xv, yv);
    const xh = r * (cos(N) * cos(v + w) - sin(N) * sin(v + w) * cos(i));
    const yh = r * (sin(N) * cos(v + w) + cos(N) * sin(v + w) * cos(i));
    const zh = r * sin(v + w) * sin(i);
    let lon = atan2(yh, xh), lat = atan2(zh, Math.hypot(xh, yh));
    const Ms = norm(356.0470 + 0.9856002585 * d), ws = 282.9404 + 4.70935e-5 * d;
    const Ls = Ms + ws, Lm = N + w + M, D = Lm - Ls, F = Lm - N;
    lon += -1.274 * sin(M - 2 * D) + 0.658 * sin(2 * D) - 0.186 * sin(Ms) - 0.059 * sin(2 * M - 2 * D)
         - 0.057 * sin(M - 2 * D + Ms) + 0.053 * sin(M + 2 * D) + 0.046 * sin(2 * D - Ms) + 0.041 * sin(M - Ms)
         - 0.035 * sin(D) - 0.031 * sin(M + Ms) - 0.015 * sin(2 * F - 2 * D) + 0.011 * sin(M - 4 * D);
    lat += -0.173 * sin(F - 2 * D) - 0.055 * sin(M - F - 2 * D) - 0.046 * sin(M + F - 2 * D)
         + 0.033 * sin(F + 2 * D) + 0.017 * sin(2 * M + F);
    r += -0.58 * cos(M - 2 * D) - 0.46 * cos(2 * D);
    const eps = 23.4393 - 3.563e-7 * d;
    const eq = eclipticToEquatorial([cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)], eps);
    return { ra: eq.ra, dec: eq.dec, dist: r, lon: norm(lon) };
  }

  // Altitude and azimuth (azimuth from north through east) for an observer.
  function horizontal(ra, dec, jd, lat, lonEast) {
    const H = gmst(jd) + lonEast - ra;
    const x = -cos(dec) * sin(H);
    const y = cos(lat) * sin(dec) - sin(lat) * cos(dec) * cos(H);
    const z = sin(lat) * sin(dec) + cos(lat) * cos(dec) * cos(H);
    return { alt: asin(z), az: norm(atan2(x, y)) };
  }

  // Everything movable, as seen from one place at one moment.
  function bodies(date, lat, lonEast) {
    const jd = julian(date);
    const out = {};
    for (const name of ['sun', 'mercury', 'venus', 'mars', 'jupiter', 'saturn']) {
      const p = planet(name, jd);
      out[name] = { ...p, ...horizontal(p.ra, p.dec, jd, lat, lonEast) };
    }
    const m = moon(jd);
    const h = horizontal(m.ra, m.dec, jd, lat, lonEast);
    // Topocentric parallax: from the Earth's surface the Moon sits up to a degree lower.
    h.alt -= asin(cos(h.alt) / m.dist);
    // Phase: elongation from the Sun, illuminated fraction, waxing or waning.
    const sun = out.sun;
    const elong = Math.acos(sin(sun.dec) * sin(m.dec) + cos(sun.dec) * cos(m.dec) * cos(sun.ra - m.ra)) / RAD;
    const sunLon = norm(atan2(sin(sun.ra) * cos(23.4393) + Math.tan(sun.dec * RAD) * sin(23.4393), cos(sun.ra)));
    out.moon = { ...m, ...h, elong, illum: (1 - cos(elong)) / 2, waxing: norm(m.lon - sunLon) < 180 };
    return out;
  }

  // Precess a J2000 star list once for a given moment: returns a function giving alt/az.
  function starProjector(date, lat, lonEast) {
    const jd = julian(date);
    const T = (jd - 2451545) / 36525;
    return (ra, dec) => {
      const p = precess(ra, dec, T);
      return horizontal(p.ra, p.dec, jd, lat, lonEast);
    };
  }

  // Times between t0 and t1 when f(time) crosses `level`, rising or setting,
  // found by stepping and then interpolating linearly.
  function crossings(f, level, t0, t1, stepMinutes = 10) {
    const out = [];
    const step = stepMinutes * 60000;
    let tPrev = t0, vPrev = f(new Date(t0)) - level;
    for (let t = t0 + step; t <= t1; t += step) {
      const v = f(new Date(t)) - level;
      if ((vPrev < 0) !== (v < 0)) {
        out.push({ time: new Date(tPrev + (step * vPrev) / (vPrev - v)), rising: v > 0 });
      }
      tPrev = t; vPrev = v;
    }
    return out;
  }

  window.Astro = { julian, gmst, planet, moon, horizontal, bodies, starProjector, crossings, precess };
})();
