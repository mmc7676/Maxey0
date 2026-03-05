export type Vec = number[];

export function add(a: Vec, b: Vec): Vec {
  const out = new Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] + b[i];
  return out;
}

export function sub(a: Vec, b: Vec): Vec {
  const out = new Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] - b[i];
  return out;
}

export function scale(a: Vec, s: number): Vec {
  const out = new Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] * s;
  return out;
}

export function dot(a: Vec, b: Vec): number {
  let x = 0;
  for (let i = 0; i < a.length; i++) x += a[i] * b[i];
  return x;
}

export function l2(a: Vec): number {
  return Math.sqrt(dot(a, a));
}

export function l2Distance(a: Vec, b: Vec): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) {
    const d = a[i] - b[i];
    s += d * d;
  }
  return Math.sqrt(s);
}

export function centroid(vs: Vec[]): Vec {
  if (vs.length === 0) return [];
  const d = vs[0].length;
  const out = new Array(d).fill(0);
  for (const v of vs) for (let j = 0; j < d; j++) out[j] += v[j];
  for (let j = 0; j < d; j++) out[j] /= vs.length;
  return out;
}

export function variance(vs: Vec[], mean?: Vec): number {
  if (vs.length === 0) return 0;
  const mu = mean ?? centroid(vs);
  let acc = 0;
  for (const v of vs) {
    let s = 0;
    for (let i = 0; i < v.length; i++) {
      const d = v[i] - mu[i];
      s += d * d;
    }
    acc += s;
  }
  return acc / vs.length;
}
