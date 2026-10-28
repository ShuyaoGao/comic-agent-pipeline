/* =====================================================================
 * pyrt.js —— 让 JS 版流水线和 Python 版“逐字段一致”所需的最小运行时
 *
 *   md5Hex(str)            与 hashlib.md5(str.encode("utf-8")).hexdigest() 相同
 *   PyRandom(seed)         与 random.Random(int) 相同：MT19937 + init_by_array 播种，
 *                          choice() 走 getrandbits 拒绝采样（_randbelow_with_getrandbits）
 *   pyRound(x, nd)         与 round(float, nd) 相同（按二进制精确值、银行家舍入）
 *   pyFloat(x) / pyFixed   与 repr(float) / format(x, ".Nf") 相同
 *   cpLen / cpSlice        按 Unicode 码点计长度与切片（Python 的 len / s[a:b]，emoji 也算 1 个）
 *   pyIsSpace / pyStrip    与 str.isspace / str.strip 相同的空白定义
 *   pyFirstNumber          与 re.search(r"(\d+(?:\.\d+)?)", s) + float() 相同（\d 含全角等 Unicode 数字）
 *   pyJson                 与 pydantic 的 model_dump_json() 相同的紧凑 JSON（浮点字段保留 ".0"）
 *
 * 纯函数、无 DOM，浏览器和 Node 测试共用。
 * ===================================================================== */
(function (root) {
  "use strict";

  /* ------------------------------------------------------------------ UTF-8 */
  function utf8Bytes(str) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(str);
    const out = [];
    for (const ch of str) {
      let c = ch.codePointAt(0);
      if (c < 0x80) out.push(c);
      else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
      else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
      else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    }
    return Uint8Array.from(out);
  }

  /* ------------------------------------------------------------------ MD5（RFC 1321） */
  const MD5_S = [7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
                 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
                 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
                 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21];
  const MD5_K = Array.from({ length: 64 }, (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32) >>> 0);

  function md5Hex(str) {
    const msg = utf8Bytes(str);
    const len = msg.length;
    const total = ((len + 8) >>> 6) + 1;            // 512 位分块数
    const words = new Uint32Array(total * 16);
    for (let i = 0; i < len; i++) words[i >> 2] |= msg[i] << ((i % 4) * 8);
    words[len >> 2] |= 0x80 << ((len % 4) * 8);
    const bitLen = len * 8;
    words[total * 16 - 2] = bitLen >>> 0;
    words[total * 16 - 1] = Math.floor(bitLen / 2 ** 32) >>> 0;
    let a0 = 0x67452301, b0 = 0xefcdab89, c0 = 0x98badcfe, d0 = 0x10325476;
    for (let blk = 0; blk < total; blk++) {
      let A = a0, B = b0, C = c0, D = d0;
      for (let i = 0; i < 64; i++) {
        let F, g;
        if (i < 16) { F = (B & C) | (~B & D); g = i; }
        else if (i < 32) { F = (D & B) | (~D & C); g = (5 * i + 1) % 16; }
        else if (i < 48) { F = B ^ C ^ D; g = (3 * i + 5) % 16; }
        else { F = C ^ (B | ~D); g = (7 * i) % 16; }
        F = (F + A + MD5_K[i] + words[blk * 16 + g]) >>> 0;
        A = D; D = C; C = B;
        B = (B + ((F << MD5_S[i]) | (F >>> (32 - MD5_S[i])))) >>> 0;
      }
      a0 = (a0 + A) >>> 0; b0 = (b0 + B) >>> 0; c0 = (c0 + C) >>> 0; d0 = (d0 + D) >>> 0;
    }
    const hex = n => [0, 8, 16, 24].map(s => ((n >>> s) & 255).toString(16).padStart(2, "0")).join("");
    return hex(a0) + hex(b0) + hex(c0) + hex(d0);
  }

  /* ------------------------------------------------------------------ MT19937（CPython _randommodule.c） */
  const N = 624, M = 397;
  class PyRandom {
    constructor(seed) {
      this.mt = new Uint32Array(N);
      this.mti = N + 1;
      this.seed(seed);
    }
    /* random.Random(int)：key = abs(n) 按 32 位小端切块；n == 0 时 key = [0] */
    seed(n) {
      let v = BigInt(n);
      if (v < 0n) v = -v;
      const key = [];
      if (v === 0n) key.push(0);
      while (v > 0n) { key.push(Number(v & 0xffffffffn)); v >>= 32n; }
      this._initByArray(key);
    }
    _initGenrand(s) {
      const mt = this.mt;
      mt[0] = s >>> 0;
      for (let i = 1; i < N; i++) {
        const prev = mt[i - 1] ^ (mt[i - 1] >>> 30);
        mt[i] = (Math.imul(1812433253, prev) + i) >>> 0;
      }
      this.mti = N;
    }
    _initByArray(key) {
      const mt = this.mt;
      this._initGenrand(19650218);
      let i = 1, j = 0;
      for (let k = Math.max(N, key.length); k; k--) {
        const prev = mt[i - 1] ^ (mt[i - 1] >>> 30);
        mt[i] = ((mt[i] ^ Math.imul(prev, 1664525)) + key[j] + j) >>> 0;
        i++; j++;
        if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
        if (j >= key.length) j = 0;
      }
      for (let k = N - 1; k; k--) {
        const prev = mt[i - 1] ^ (mt[i - 1] >>> 30);
        mt[i] = ((mt[i] ^ Math.imul(prev, 1566083941)) - i) >>> 0;
        i++;
        if (i >= N) { mt[0] = mt[N - 1]; i = 1; }
      }
      mt[0] = 0x80000000;
      this.mti = N;
    }
    genrandUint32() {
      const mt = this.mt;
      if (this.mti >= N) {
        let kk = 0, y;
        for (; kk < N - M; kk++) {
          y = (mt[kk] & 0x80000000) | (mt[kk + 1] & 0x7fffffff);
          mt[kk] = mt[kk + M] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        }
        for (; kk < N - 1; kk++) {
          y = (mt[kk] & 0x80000000) | (mt[kk + 1] & 0x7fffffff);
          mt[kk] = mt[kk + (M - N)] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        }
        y = (mt[N - 1] & 0x80000000) | (mt[0] & 0x7fffffff);
        mt[N - 1] = mt[M - 1] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0);
        this.mti = 0;
      }
      let y = mt[this.mti++];
      y ^= y >>> 11;
      y ^= (y << 7) & 0x9d2c5680;
      y ^= (y << 15) & 0xefc60000;
      y ^= y >>> 18;
      return y >>> 0;
    }
    getrandbits(k) {                     // 本项目只用到 k ≤ 32
      if (k <= 0) return 0;
      if (k > 32) throw new Error("getrandbits: k > 32 not supported");
      return this.genrandUint32() >>> (32 - k);
    }
    random() {
      const a = this.genrandUint32() >>> 5, b = this.genrandUint32() >>> 6;
      return (a * 67108864 + b) / 9007199254740992;
    }
    _randbelow(n) {
      const k = n.toString(2).length;   // int.bit_length()
      let r = this.getrandbits(k);
      while (r >= n) r = this.getrandbits(k);
      return r;
    }
    choice(seq) {
      if (!seq.length) throw new Error("Cannot choose from an empty sequence");
      return seq[this._randbelow(seq.length)];
    }
  }

  /* ------------------------------------------------------------------ 浮点：精确十进制 */
  // 把 double 拆成 (sign, BigInt 尾数 m, 二进制指数 e)，使 |x| = m · 2^e
  function decompose(x) {
    const dv = new DataView(new ArrayBuffer(8));
    dv.setFloat64(0, x);
    const hi = dv.getUint32(0), lo = dv.getUint32(4);
    const sign = hi >>> 31 ? -1 : 1;
    const expBits = (hi >>> 20) & 0x7ff;
    let mant = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
    let e;
    if (expBits === 0) e = -1074;
    else { mant |= 1n << 52n; e = expBits - 1075; }
    return { sign, m: mant, e };
  }
  // |x| 乘 10^nd 后按“二进制精确值 + 银行家舍入”取整，返回 BigInt
  function scaledRoundHalfEven(x, nd) {
    const { m, e } = decompose(x);
    let num = m, den = 1n;
    if (e >= 0) num <<= BigInt(e); else den <<= BigInt(-e);
    if (nd >= 0) num *= 10n ** BigInt(nd); else den *= 10n ** BigInt(-nd);
    let q = num / den;
    const r2 = (num % den) * 2n;
    if (r2 > den || (r2 === den && (q & 1n) === 1n)) q += 1n;
    return q;
  }
  function decimalString(q, nd) {       // BigInt q 视为 q / 10^nd，nd ≥ 0
    let s = q.toString();
    if (nd === 0) return s;
    s = s.padStart(nd + 1, "0");
    return s.slice(0, s.length - nd) + "." + s.slice(s.length - nd);
  }
  /* round(x, nd) —— Python 对 float 的 round（nd ≥ 0） */
  function pyRound(x, nd = 0) {
    if (!Number.isFinite(x) || x === 0) return x;
    const q = scaledRoundHalfEven(x, nd);
    const v = Number(decimalString(q, nd));
    return x < 0 ? -v : v;
  }
  /* format(x, ".Nf") */
  function pyFixed(x, nd) {
    if (!Number.isFinite(x)) return x > 0 ? "inf" : x < 0 ? "-inf" : "nan";
    const neg = x < 0 || Object.is(x, -0);
    return (neg ? "-" : "") + decimalString(scaledRoundHalfEven(Math.abs(x), nd), nd);
  }
  /* repr(float)：最短往返数字；-4 ≤ 指数 < 16 用定点，否则科学计数（指数至少 2 位） */
  function pyFloat(x) {
    if (Number.isNaN(x)) return "nan";
    if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
    if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
    const neg = x < 0;
    const [mant, expStr] = Math.abs(x).toExponential().split("e");
    const digits = mant.replace(".", "");
    const exp = parseInt(expStr, 10);
    let s;
    if (exp >= -4 && exp < 16) {
      if (exp >= 0) {
        const ip = digits.slice(0, exp + 1).padEnd(exp + 1, "0");
        const fp = digits.slice(exp + 1) || "0";
        s = ip + "." + fp;
      } else s = "0." + "0".repeat(-exp - 1) + digits;
    } else {
      s = digits[0] + (digits.length > 1 ? "." + digits.slice(1) : "") + "e" + (exp < 0 ? "-" : "+") +
          String(Math.abs(exp)).padStart(2, "0");
    }
    return (neg ? "-" : "") + s;
  }
  /* 把“Python 里是 float”的数值转成 f-string 里的样子；整数类型请直接用 String() */
  const pyNum = (x, isFloat) => (isFloat ? pyFloat(x) : String(x));

  /* Python 的 % 与 // 对负数的语义 */
  const pyMod = (a, b) => ((a % b) + b) % b;
  const pyFloorDiv = (a, b) => Math.floor(a / b);

  /* ------------------------------------------------------------------ 字符串（按码点） */
  const cps = s => Array.from(s);
  const cpLen = s => cps(s).length;
  function cpSlice(s, a, b) {
    const arr = cps(s);
    return arr.slice(a, b === undefined ? arr.length : b).join("");
  }
  // str.isspace() 的字符集合（CPython：Zs 类、以及双向类别 WS/B/S）
  const PY_SPACE = new Set([0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
    0x2028, 0x2029, 0x202f, 0x205f, 0x3000]);
  const pyIsSpace = ch => ch.length > 0 && cps(ch).every(c => PY_SPACE.has(c.codePointAt(0)));
  function pyStrip(s) {
    const a = cps(s);
    let i = 0, j = a.length;
    while (i < j && PY_SPACE.has(a[i].codePointAt(0))) i++;
    while (j > i && PY_SPACE.has(a[j - 1].codePointAt(0))) j--;
    return a.slice(i, j).join("");
  }

  /* re.search(r"(\d+(?:\.\d+)?)", s) → float(...)；Python 的 \d 匹配所有 Unicode 十进制数字 */
  const ND = /\p{Nd}/u;
  function ndValue(ch) {
    let cp = ch.codePointAt(0), z = cp;
    while (ND.test(String.fromCodePoint(z - 1))) z--;   // Unicode 的十进制数字都是从 0 开始连续 10 个
    return (cp - z) % 10;
  }
  function pyFirstNumber(text, dflt) {
    const m = /(\p{Nd}+(?:\.\p{Nd}+)?)/u.exec(text || "");
    if (!m) return dflt;
    const ascii = cps(m[1]).map(c => (c === "." ? "." : String(ndValue(c)))).join("");
    return parseFloat(ascii);
  }

  /* Python 里 str(list_of_str)（只用于合规命中词列表；命中词都是普通汉字） */
  function pyReprStr(s) {
    const q = s.includes("'") && !s.includes('"') ? '"' : "'";
    let out = "";
    for (const ch of s) {
      const c = ch.codePointAt(0);
      if (ch === "\\") out += "\\\\";
      else if (ch === q) out += "\\" + q;
      else if (ch === "\n") out += "\\n";
      else if (ch === "\r") out += "\\r";
      else if (ch === "\t") out += "\\t";
      else if (c < 0x20 || c === 0x7f) out += "\\x" + c.toString(16).padStart(2, "0");
      else out += ch;
    }
    return q + out + q;
  }
  const pyReprList = list => "[" + list.map(pyReprStr).join(", ") + "]";

  /* ------------------------------------------------------------------ pydantic model_dump_json() */
  function jsonStr(s) {
    let out = '"';
    for (const ch of s) {
      const c = ch.codePointAt(0);
      if (ch === '"') out += '\\"';
      else if (ch === "\\") out += "\\\\";
      else if (ch === "\n") out += "\\n";
      else if (ch === "\r") out += "\\r";
      else if (ch === "\t") out += "\\t";
      else if (ch === "\b") out += "\\b";
      else if (ch === "\f") out += "\\f";
      else if (c < 0x20) out += "\\u" + c.toString(16).padStart(4, "0");
      else out += ch;
    }
    return out + '"';
  }
  /* floatKeys：哪些字段在 schema 里是 float（整数值也要输出 "8.0"） */
  function pyJson(v, floatKeys, key) {
    if (v === null || v === undefined) return "null";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "number") return floatKeys && floatKeys.has(key) ? pyFloat(v) : String(v);
    if (typeof v === "string") return jsonStr(v);
    if (Array.isArray(v)) return "[" + v.map(x => pyJson(x, floatKeys, key)).join(",") + "]";
    return "{" + Object.keys(v).map(k => jsonStr(k) + ":" + pyJson(v[k], floatKeys, k)).join(",") + "}";
  }

  root.PyRT = { md5Hex, PyRandom, pyRound, pyFixed, pyFloat, pyNum, pyMod, pyFloorDiv,
                cpLen, cpSlice, pyIsSpace, pyStrip, pyFirstNumber, pyReprList, pyJson, utf8Bytes };
})(typeof window !== "undefined" ? window : globalThis);
