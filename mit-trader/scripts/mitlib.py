# Reviewed for local use
"""mitlib: the shared math of the MIT Trader skill.

Standard-library Python only (3.8+). Every tool in scripts/ imports it.

The math follows MIT 18.S096 "Topics in Mathematics with Applications in
Finance" (Fall 2013, MIT OpenCourseWare). Lecture numbers are noted next to
each piece (L6 = Lecture 6, Regression Analysis, and so on).
"""

import datetime as _dt
import hashlib
import json
import math
import os
import random
import time
import urllib.request

VERSION = "1.0.0"
SEED = 18  # 18.S096: every simulation is repeatable with the same seed

# ---------------------------------------------------------------------------
# files and config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "budget": 10000,
    "paper": True,
    "broker": "alpaca",
    "universe": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX",
        "JPM", "GS", "WFC", "V", "COST", "LLY", "UNH", "PEP", "PG", "JNJ", "CVX", "MU",
        "PLTR", "UBER", "INTC", "QCOM", "AMAT", "LRCX", "KLAC", "NEM",
        "SPY", "QQQ", "IWM", "TLT", "IEF", "GLD", "GDX", "XLE", "SOXX", "KRE", "LQD",
        "BTC-USD", "ETH-USD",
    ],
    "benchmark": "SPY",
    "horizon_days": 5,
    "lookback_days": 756,
    "stop_sigma": 1.0,
    "target_sigma": 2.0,
    "kelly_fraction": 0.5,
    "cash_buffer_pct": 10,
    "max_position_pct": 25,
    "max_order_usd": 5000,
    "min_order_usd": 10,
    "max_loss_per_trade_usd": 100,
    "max_daily_loss_usd": 300,
    "max_trades_per_day": 3,
    "max_orders_per_day": 10,
    "min_reward_risk": 1.5,
    "max_var_pct": 5.0,
    "var_confidence": 0.99,
    "require_stop": True,
    "require_edge": False,
    "no_entries_before": "09:45",
    "no_entries_after": "15:45",
    "fractional": False,
    "allow_crypto": True,
    "allow_short": False,
    "allow_margin": False,
    "allow_options": False,
    "blocked": [],
}


def mit_dir():
    """The working folder every skill reads and writes: ./mit, or $MIT_DIR."""
    return os.environ.get("MIT_DIR") or os.path.join(os.getcwd(), "mit")


def path(*parts):
    return os.path.join(mit_dir(), *parts)


def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(p, obj):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, p)


def load_config(p=None):
    cfg = dict(DEFAULT_CONFIG)
    user = load_json(p or path("config.json"), {}) or {}
    cfg.update(user)
    return cfg


def fingerprint(obj):
    """A short hash of an exact order, so a verdict cannot be reused for an edited one."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# symbols and data
# ---------------------------------------------------------------------------

CRYPTO = ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LTC", "AVAX", "LINK", "DOT", "BCH")


def norm_symbol(sym):
    """BTC, BTC/USD, btcusd -> BTC-USD (Yahoo's spelling). Stocks: upper case."""
    s = str(sym).strip().upper().replace(" ", "")
    for c in CRYPTO:
        if s in (c, c + "/USD", c + "USD", c + "-USD", c + "USDT", c + "/USDT"):
            return c + "-USD"
    return s.replace("/", "-")


def is_crypto(sym):
    s = norm_symbol(sym)
    return s.endswith("-USD") and s.split("-")[0] in CRYPTO


def broker_symbol(sym):
    """Alpaca spells crypto BTC/USD."""
    s = norm_symbol(sym)
    return s.replace("-", "/") if is_crypto(s) else s


def asset_class(sym):
    return "crypto" if is_crypto(sym) else "us_equity"


YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=1d&includeAdjustedClose=true&events=div%%2Csplits"
UA = "Mozilla/5.0 (mit-trader-skill; +https://github.com/roan-maverick/MIT-trader-skill)"


def _utc(ts):
    """A naive UTC datetime from a Unix timestamp."""
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).replace(tzinfo=None)


def parse_yahoo_chart(doc, symbol=None):
    """Yahoo's chart JSON -> {dates, close (adjusted), open, high, low, volume, last}."""
    res = (doc.get("chart") or {}).get("result") or []
    if not res:
        err = (doc.get("chart") or {}).get("error")
        raise ValueError("no data for %s: %s" % (symbol, err))
    r = res[0]
    meta = r.get("meta") or {}
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((r.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
    off = int(meta.get("gmtoffset") or 0)
    out = {"symbol": norm_symbol(symbol or meta.get("symbol", "")), "source": "yahoo",
           "dates": [], "close": [], "open": [], "high": [], "low": [], "volume": []}
    closes = adj if adj else q.get("close") or []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        raw = (q.get("close") or [None] * len(ts))[i]
        k = (c / raw) if raw else 1.0  # adjust OHLC by the same factor as the close
        d = _utc(t + off).strftime("%Y-%m-%d")
        if out["dates"] and out["dates"][-1] == d:
            out["dates"].pop(); out["close"].pop(); out["open"].pop()
            out["high"].pop(); out["low"].pop(); out["volume"].pop()
        out["dates"].append(d)
        out["close"].append(round(float(c), 6))
        for f in ("open", "high", "low"):
            v = (q.get(f) or [None] * len(ts))[i]
            out[f].append(round(float(v) * k, 6) if v is not None else None)
        v = (q.get("volume") or [None] * len(ts))[i]
        out["volume"].append(int(v) if v is not None else None)
    if meta.get("regularMarketPrice") is not None:
        out["last"] = {"price": float(meta["regularMarketPrice"]),
                       "time": _utc(int(meta.get("regularMarketTime") or 0)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return out


def fetch_yahoo(symbol, rng="10y", retries=2):
    url = YAHOO % (urllib.request.quote(norm_symbol(symbol)), rng)
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as fh:
                return parse_yahoo_chart(json.loads(fh.read().decode("utf-8")), symbol)
        except Exception as e:  # network, rate limit, bad symbol
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("could not fetch %s from Yahoo: %s" % (symbol, last_err))


def load_bars(symbol, data_dir=None, refresh=False, max_age_hours=12):
    """Daily bars for one symbol.

    data_dir: a folder of SYMBOL.json files (offline, used by the tests and the
    worked example). Otherwise mit/bars/ is a cache, refreshed from Yahoo when
    older than max_age_hours.
    """
    sym = norm_symbol(symbol)
    fname = sym.replace("^", "_") + ".json"
    if data_dir and os.path.isfile(data_dir):  # a bundle: {SYMBOL: {dates, close}}, .json or .json.gz
        bundle = _bundle(data_dir)
        if sym not in bundle:
            raise RuntimeError("no bars for %s in %s" % (sym, data_dir))
        return dict(bundle[sym], symbol=sym)
    if data_dir:
        doc = load_json(os.path.join(data_dir, fname))
        if not doc:
            raise RuntimeError("no bars for %s in %s" % (sym, data_dir))
        return doc
    cache = path("bars", fname)
    doc = load_json(cache)
    fresh = doc and (time.time() - os.path.getmtime(cache)) < max_age_hours * 3600
    if refresh or not fresh:
        try:
            doc = fetch_yahoo(sym)
            save_json(cache, doc)
        except RuntimeError:
            if not doc:
                raise
    return doc


_BUNDLES = {}


def _bundle(p):
    if p not in _BUNDLES:
        import gzip
        opener = gzip.open if p.endswith(".gz") else open
        with opener(p, "rt", encoding="utf-8") as fh:
            _BUNDLES[p] = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}
    return _BUNDLES[p]


def bundle_symbols(p):
    return sorted(_bundle(p))


def closes(bars, asof=None, lookback=None):
    """(dates, closes) up to and including asof (YYYY-MM-DD), last `lookback` rows."""
    d, c = bars["dates"], bars["close"]
    if asof:
        n = len(d)
        while n and d[n - 1] > asof:
            n -= 1
        d, c = d[:n], c[:n]
    pairs = [(x, y) for x, y in zip(d, c) if y is not None and y > 0]
    if lookback:
        pairs = pairs[-lookback:]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def align(series):
    """{sym: (dates, values)} -> (common dates, {sym: values}) on dates all share."""
    common = None
    for d, _ in series.values():
        common = set(d) if common is None else common & set(d)
    dates = sorted(common or [])
    out = {}
    for s, (d, v) in series.items():
        m = dict(zip(d, v))
        out[s] = [m[x] for x in dates]
    return dates, out


# ---------------------------------------------------------------------------
# basic statistics (L3)
# ---------------------------------------------------------------------------

def mean(x):
    return sum(x) / len(x) if x else float("nan")


def var(x, ddof=1):
    n = len(x)
    if n <= ddof:
        return float("nan")
    m = mean(x)
    return sum((v - m) ** 2 for v in x) / (n - ddof)


def std(x, ddof=1):
    v = var(x, ddof)
    return math.sqrt(v) if v == v and v >= 0 else float("nan")


def cov(x, y, ddof=1):
    mx, my = mean(x), mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - ddof)


def corr(x, y):
    sx, sy = std(x), std(y)
    return cov(x, y) / (sx * sy) if sx > 0 and sy > 0 else float("nan")


def quantile(x, q):
    s = sorted(x)
    if not s:
        return float("nan")
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def skew(x):
    m, s = mean(x), std(x, 0)
    return sum(((v - m) / s) ** 3 for v in x) / len(x) if s > 0 else float("nan")


def kurtosis(x):
    """Excess kurtosis (normal = 0). Fat tails show up here (L9)."""
    m, s = mean(x), std(x, 0)
    return sum(((v - m) / s) ** 4 for v in x) / len(x) - 3 if s > 0 else float("nan")


def log_returns(prices):
    return [math.log(b / a) for a, b in zip(prices[:-1], prices[1:])]


def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def norm_cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


def norm_ppf(p):
    """Inverse normal CDF (Acklam's rational approximation, ~1e-9 accurate)."""
    if p <= 0 or p >= 1:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    elif p > hi:
        q = math.sqrt(-2 * math.log(1 - p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    else:
        q = p - 0.5
        r = q * q
        x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
            (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    # one Newton step polishes it
    e = norm_cdf(x) - p
    return x - e * math.sqrt(2 * math.pi) * math.exp(x * x / 2)


def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(c) > 1e-300 else 1e300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(c) > 1e-300 else 1e300
        de = d * c
        h *= de
        if abs(de - 1) < 1e-12:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return 1 - p if t > 0 else p


def t_pvalue(t, df):
    """Two-sided p-value of a t statistic."""
    if t != t:
        return float("nan")
    return 2 * (1 - t_cdf(abs(t), df))


def chi2_sf(x, k):
    """P(chi2_k > x) via the regularized upper incomplete gamma."""
    if x <= 0:
        return 1.0
    a = k / 2.0
    xx = x / 2.0
    if xx < a + 1:  # series
        s, term, n = 1.0 / a, 1.0 / a, 0
        while abs(term) > 1e-14 * abs(s) and n < 1000:
            n += 1
            term *= xx / (a + n)
            s += term
        return 1 - s * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
    b = xx + 1 - a  # continued fraction
    c, d = 1e300, 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = b + an / c if abs(c) > 1e-300 else 1e300
        de = d * c
        h *= de
        if abs(de - 1) < 1e-14:
            break
    return math.exp(-xx + a * math.log(xx) - math.lgamma(a)) * h


# ---------------------------------------------------------------------------
# linear algebra (L2, L4)
# ---------------------------------------------------------------------------

def transpose(A):
    return [list(r) for r in zip(*A)]


def matmul(A, B):
    Bt = transpose(B)
    return [[sum(a * b for a, b in zip(row, col)) for col in Bt] for row in A]


def matvec(A, v):
    return [sum(a * b for a, b in zip(row, v)) for row in A]


def dot(u, v):
    return sum(a * b for a, b in zip(u, v))


def eye(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def solve(A, b):
    """Solve A x = b by Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [list(map(float, A[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-14:
            raise ValueError("singular matrix")
        M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            if f:
                for k in range(col, n + 1):
                    M[r][k] -= f * M[col][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][k] * x[k] for k in range(i + 1, n))) / M[i][i]
    return x


def inv(A):
    n = len(A)
    cols = [solve(A, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return transpose(cols)


def cholesky(A):
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = A[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 0:
                    s = 1e-12  # tiny jitter keeps a near-singular covariance usable
                L[i][j] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    return L


def eig_sym(A, tol=1e-12, max_sweeps=100):
    """Eigenvalues and eigenvectors of a symmetric matrix (cyclic Jacobi).

    Returns (values, vectors) sorted by value, largest first; vectors[k] is
    the k-th eigenvector. L2: symmetric matrices have real eigenvalues and an
    orthonormal eigenbasis, which is what makes PCA work.
    """
    n = len(A)
    a = [list(map(float, r)) for r in A]
    v = eye(n)
    for _ in range(max_sweeps):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < tol:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1 if theta >= 0 else -1) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    vals = [a[i][i] for i in range(n)]
    order = sorted(range(n), key=lambda i: -vals[i])
    vecs = []
    for i in order:
        vec = [v[k][i] for k in range(n)]
        if sum(vec) < 0:  # sign convention: loadings mostly positive
            vec = [-x for x in vec]
        vecs.append(vec)
    return [vals[i] for i in order], vecs


def cov_matrix(R):
    """Sample covariance of columns. R: list of rows (time) x assets."""
    n, k = len(R), len(R[0])
    mu = [sum(r[j] for r in R) / n for j in range(k)]
    C = [[0.0] * k for _ in range(k)]
    for r in R:
        d = [r[j] - mu[j] for j in range(k)]
        for i in range(k):
            di = d[i]
            row = C[i]
            for j in range(i, k):
                row[j] += di * d[j]
    for i in range(k):
        for j in range(i, k):
            C[i][j] /= (n - 1)
            C[j][i] = C[i][j]
    return C


def ledoit_wolf(R):
    """Shrinkage covariance (L10: regularize a noisy estimate toward a simple target).

    Ledoit-Wolf (2004) shrinkage toward a scaled identity. Returns (Sigma, delta)
    where delta in [0, 1] is how far it was pulled toward the target.
    """
    n, k = len(R), len(R[0])
    mu = [sum(r[j] for r in R) / n for j in range(k)]
    X = [[r[j] - mu[j] for j in range(k)] for r in R]
    S = [[sum(x[i] * x[j] for x in X) / n for j in range(k)] for i in range(k)]
    m = sum(S[i][i] for i in range(k)) / k
    d2 = sum((S[i][j] - (m if i == j else 0.0)) ** 2 for i in range(k) for j in range(k)) / k
    b2 = 0.0
    for x in X:
        b2 += sum((x[i] * x[j] - S[i][j]) ** 2 for i in range(k) for j in range(k)) / k
    b2 /= n * n
    b2 = min(b2, d2)
    delta = b2 / d2 if d2 > 0 else 0.0
    Sig = [[delta * (m if i == j else 0.0) + (1 - delta) * S[i][j] for j in range(k)] for i in range(k)]
    return Sig, delta


# ---------------------------------------------------------------------------
# regression (L6)
# ---------------------------------------------------------------------------

def ols(y, X, add_const=True, nw_lags=0):
    """Ordinary least squares with classical or Newey-West standard errors.

    y: list, X: list of rows (or a flat list for one regressor).
    nw_lags > 0 uses Newey-West (HAC) errors, needed when the y's overlap in
    time (for example 5-day returns sampled every day).
    """
    if X and not isinstance(X[0], (list, tuple)):
        X = [[v] for v in X]
    if add_const:
        X = [[1.0] + list(r) for r in X]
    n, p = len(y), len(X[0])
    XtX = [[sum(X[t][i] * X[t][j] for t in range(n)) for j in range(p)] for i in range(p)]
    Xty = [sum(X[t][i] * y[t] for t in range(n)) for i in range(p)]
    XtX_inv = inv(XtX)
    beta = matvec(XtX_inv, Xty)
    fitted = [dot(X[t], beta) for t in range(n)]
    resid = [y[t] - fitted[t] for t in range(n)]
    sse = sum(e * e for e in resid)
    dfree = max(n - p, 1)
    s2 = sse / dfree
    if nw_lags > 0:
        S = [[0.0] * p for _ in range(p)]
        for t in range(n):
            for i in range(p):
                for j in range(p):
                    S[i][j] += resid[t] ** 2 * X[t][i] * X[t][j]
        for L in range(1, nw_lags + 1):
            w = 1 - L / (nw_lags + 1.0)
            for t in range(L, n):
                e = resid[t] * resid[t - L]
                for i in range(p):
                    for j in range(p):
                        S[i][j] += w * e * (X[t][i] * X[t - L][j] + X[t - L][i] * X[t][j])
        V = matmul(matmul(XtX_inv, S), XtX_inv)
        V = [[v * n / dfree for v in row] for row in V]
    else:
        V = [[v * s2 for v in row] for row in XtX_inv]
    se = [math.sqrt(max(V[i][i], 0)) for i in range(p)]
    tstat = [beta[i] / se[i] if se[i] > 0 else float("nan") for i in range(p)]
    ybar = mean(y)
    sst = sum((v - ybar) ** 2 for v in y)
    return {
        "beta": beta, "se": se, "t": tstat, "p": [t_pvalue(t, dfree) for t in tstat],
        "r2": 1 - sse / sst if sst > 0 else float("nan"), "resid": resid, "sigma": math.sqrt(s2),
        "n": n, "df": dfree,
    }


def bonferroni_t(n_tests, alpha=0.05):
    """|t| needed so that n_tests tries still have a 5% family-wise false alarm rate."""
    return norm_ppf(1 - alpha / (2.0 * max(n_tests, 1)))


# ---------------------------------------------------------------------------
# time series (L8, L11, L12)
# ---------------------------------------------------------------------------

def acf(x, lags=10):
    m = mean(x)
    d = [v - m for v in x]
    c0 = sum(v * v for v in d)
    return [sum(d[t] * d[t - k] for t in range(k, len(d))) / c0 for k in range(1, lags + 1)]


def ljung_box(x, lags=10):
    n = len(x)
    r = acf(x, lags)
    q = n * (n + 2) * sum(r[k] ** 2 / (n - k - 1) for k in range(lags))
    return q, chi2_sf(q, lags)


def ar1(x):
    """x_t = c + phi x_{t-1} + e_t. Returns phi, c, mean level, half-life (days)."""
    fit = ols(x[1:], x[:-1])
    c, phi = fit["beta"]
    hl = math.log(0.5) / math.log(phi) if 0 < phi < 1 else float("inf")
    level = c / (1 - phi) if phi != 1 else float("nan")
    return {"phi": phi, "c": c, "level": level, "half_life": hl, "sigma": fit["sigma"],
            "t_phi_minus_1": (phi - 1) / fit["se"][1] if fit["se"][1] > 0 else float("nan")}


# MacKinnon (2010) response-surface critical values: tau_inf + b1/T + b2/T^2 + b3/T^3
_MACKINNON = {
    # unit-root ADF test with a constant
    1: {0.01: (-3.43035, -6.5393, -16.786, -79.433), 0.05: (-2.86154, -2.8903, -4.234, -40.040),
        0.10: (-2.56677, -1.5384, -2.809, 0.0)},
    # Engle-Granger cointegration test, 2 variables, with a constant
    2: {0.01: (-3.89644, -10.9519, -22.527, 0.0), 0.05: (-3.33613, -6.1101, -6.823, 0.0),
        0.10: (-3.04445, -4.2412, -2.720, 0.0)},
}


def mackinnon_crit(n_vars, T):
    tab = _MACKINNON[n_vars]
    return {lvl: c[0] + c[1] / T + c[2] / T ** 2 + c[3] / T ** 3 for lvl, c in tab.items()}


def adf(x, lags=1, n_vars=1):
    """Augmented Dickey-Fuller test (L8): is x mean-reverting (stationary)?

    Regress dx_t on x_{t-1} and lagged dx. The t statistic on x_{t-1} is
    compared with MacKinnon critical values. More negative = stronger
    evidence of mean reversion. n_vars=2 gives Engle-Granger critical values
    for the residual of a 2-asset cointegrating regression (L12).
    """
    dx = [b - a for a, b in zip(x[:-1], x[1:])]
    rows, ys = [], []
    for t in range(lags, len(dx)):
        rows.append([x[t]] + [dx[t - k] for k in range(1, lags + 1)])
        ys.append(dx[t])
    fit = ols(ys, rows)
    tau = fit["t"][1]
    crit = mackinnon_crit(n_vars, len(ys))
    level = None
    for lvl in (0.01, 0.05, 0.10):
        if tau < crit[lvl]:
            level = lvl
            break
    return {"stat": tau, "crit": crit, "reject_at": level, "n": len(ys), "lags": lags}


def kalman_beta(y, x, delta=1e-4, obs_var=None):
    """Time-varying regression y_t = a_t + b_t x_t + e_t (L12: linear state-space model).

    State (a_t, b_t) follows a random walk with variance delta/(1-delta) per step.
    Returns lists of a_t, b_t and the one-step forecast errors and their variances.
    """
    Vw = delta / (1 - delta)
    if obs_var is None:
        fit = ols(y[:min(len(y), 60)], x[:min(len(x), 60)])
        obs_var = fit["sigma"] ** 2
    theta = [0.0, 0.0]
    P = [[1.0, 0.0], [0.0, 1.0]]
    A, B, E, Q = [], [], [], []
    for t in range(len(y)):
        F = [1.0, x[t]]
        R = [[P[0][0] + Vw, P[0][1]], [P[1][0], P[1][1] + Vw]]
        yhat = theta[0] + theta[1] * x[t]
        e = y[t] - yhat
        RF = [R[0][0] * F[0] + R[0][1] * F[1], R[1][0] * F[0] + R[1][1] * F[1]]
        q = F[0] * RF[0] + F[1] * RF[1] + obs_var
        K = [RF[0] / q, RF[1] / q]
        theta = [theta[0] + K[0] * e, theta[1] + K[1] * e]
        P = [[R[i][j] - K[i] * RF[j] for j in range(2)] for i in range(2)]
        A.append(theta[0]); B.append(theta[1]); E.append(e); Q.append(q)
    return {"alpha": A, "beta": B, "err": E, "err_var": Q}


# ---------------------------------------------------------------------------
# optimization
# ---------------------------------------------------------------------------

def nelder_mead(f, x0, step=0.1, tol=1e-9, max_iter=3000):
    n = len(x0)
    pts = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step if p[i] == 0 else step * abs(p[i]) + step
        pts.append(p)
    vals = [f(p) for p in pts]
    for _ in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol * (abs(vals[0]) + tol):
            break
        cen = [sum(p[i] for p in pts[:-1]) / n for i in range(n)]
        xr = [cen[i] + (cen[i] - pts[-1][i]) for i in range(n)]
        fr = f(xr)
        if vals[0] <= fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        elif fr < vals[0]:
            xe = [cen[i] + 2 * (cen[i] - pts[-1][i]) for i in range(n)]
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        else:
            xc = [cen[i] + 0.5 * (pts[-1][i] - cen[i]) for i in range(n)]
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for j in range(1, n + 1):
                    pts[j] = [pts[0][i] + 0.5 * (pts[j][i] - pts[0][i]) for i in range(n)]
                    vals[j] = f(pts[j])
    i = min(range(n + 1), key=lambda k: vals[k])
    return pts[i], vals[i]


# ---------------------------------------------------------------------------
# volatility (L9)
# ---------------------------------------------------------------------------

def ewma_var(r, lam=0.94):
    """RiskMetrics exponentially weighted variance; returns the series of variances."""
    v = var(r[:30]) if len(r) > 30 else var(r)
    out = []
    for x in r:
        out.append(v)
        v = lam * v + (1 - lam) * x * x
    out.append(v)
    return out  # out[t] is the forecast for r[t]; out[-1] is tomorrow's


def _garch_filter(r, omega, alpha, beta, v0):
    v = v0
    out = []
    for x in r:
        out.append(v)
        v = omega + alpha * x * x + beta * v
    out.append(v)
    return out


def garch11(r):
    """Gaussian GARCH(1,1) by maximum likelihood (L9).

    sigma^2_t = omega + alpha r^2_{t-1} + beta sigma^2_{t-1}
    r: de-meaned daily log returns. Returns parameters, today's conditional
    variance forecast for tomorrow, the long-run variance and the filtered
    series of variances.
    """
    m = mean(r)
    x = [v - m for v in r]
    s2 = var(x)

    def unpack(p):
        a = 1 / (1 + math.exp(-p[0]))      # alpha + beta in (0, 1)
        w = 1 / (1 + math.exp(-p[1]))      # share of it that is alpha
        persist = 0.999 * a
        alpha = persist * w
        beta = persist - alpha
        lr = s2 * math.exp(max(min(p[2], 5), -5))  # long-run variance, free (full MLE)
        omega = lr * (1 - persist)
        return omega, alpha, beta

    def nll(p):
        omega, alpha, beta = unpack(p)
        vs = _garch_filter(x, omega, alpha, beta, s2)
        tot = 0.0
        for xi, vi in zip(x, vs):
            if vi <= 0:
                return 1e100
            tot += math.log(vi) + xi * xi / vi
        return 0.5 * tot

    best = None
    for start in ([2.5, -2.0, 0.0], [3.5, -2.5, 0.3], [1.5, -1.0, -0.3]):
        p, f = nelder_mead(nll, start, step=0.5, tol=1e-12)
        p, f = nelder_mead(nll, p, step=0.1, tol=1e-12)  # restart polishes the optimum
        if best is None or f < best[1]:
            best = (p, f)
    omega, alpha, beta = unpack(best[0])
    vs = _garch_filter(x, omega, alpha, beta, s2)
    persist = alpha + beta
    return {"omega": omega, "alpha": alpha, "beta": beta, "persistence": persist,
            "long_run_var": omega / (1 - persist) if persist < 1 else float("inf"),
            "var_next": vs[-1], "variances": vs, "loglik": -best[1] - 0.5 * len(x) * math.log(2 * math.pi),
            "mean": m, "half_life": math.log(0.5) / math.log(persist) if 0 < persist < 1 else float("inf")}


def garch_forecast(g, h):
    """Per-day variance forecasts for the next h days; they decay to the long-run level."""
    out, v = [], g["var_next"]
    lr, ph = g["long_run_var"], g["persistence"]
    for k in range(h):
        out.append(lr + ph ** k * (v - lr))
    return out


# ---------------------------------------------------------------------------
# stochastic processes and Monte Carlo (L5, L17, L18, L21)
# ---------------------------------------------------------------------------

def bridge_cross_prob(x0, x1, barrier, var_step):
    """Probability a Brownian path from x0 to x1 (log prices) touched `barrier` in between.

    L17: the reflection principle for Brownian motion. Lets a daily
    simulation catch stops hit during the day, not only at the close.
    """
    if var_step <= 0:
        return 0.0
    a, b = x0 - barrier, x1 - barrier
    if a * b <= 0:
        return 1.0
    return math.exp(-2 * a * b / var_step)


def first_passage(paths_fn, n, entry, stop, target, horizon, rng, side="buy"):
    """Run n simulated paths; count which of target / stop each touches first."""
    hit_t = hit_s = neither = 0
    pnl = []
    ends = []
    lt, ls = math.log(target), math.log(stop)
    for _ in range(n):
        x = math.log(entry)
        outcome = None
        for step_var, dx in paths_fn(rng, horizon):
            x1 = x + dx
            if side == "buy":
                ps = bridge_cross_prob(x, x1, ls, step_var) if x1 > ls else 1.0
                pt = bridge_cross_prob(x, x1, lt, step_var) if x1 < lt else 1.0
            else:
                ps = bridge_cross_prob(x, x1, ls, step_var) if x1 < ls else 1.0
                pt = bridge_cross_prob(x, x1, lt, step_var) if x1 > lt else 1.0
            s_hit = rng.random() < ps
            t_hit = rng.random() < pt
            if s_hit and t_hit:  # both in one step: assume the worse one (the stop)
                outcome = "stop"
            elif s_hit:
                outcome = "stop"
            elif t_hit:
                outcome = "target"
            x = x1
            if outcome:
                break
        if outcome == "target":
            hit_t += 1
            px = target
        elif outcome == "stop":
            hit_s += 1
            px = stop
        else:
            neither += 1
            px = math.exp(x)
        ends.append(math.exp(x))
        pnl.append((px - entry) if side == "buy" else (entry - px))
    return {"target": hit_t / n, "stop": hit_s / n, "neither": neither / n, "pnl": pnl, "ends": ends}


def gbm_steps(mu, sigma):
    """Daily log steps of geometric Brownian motion (L18: Ito's lemma gives the -sigma^2/2)."""
    def fn(rng, h):
        for _ in range(h):
            yield sigma * sigma, (mu - 0.5 * sigma * sigma) + sigma * rng.gauss(0, 1)
    return fn


def garch_steps(g, std_resid, mu=0.0):
    """Filtered historical simulation: GARCH variance, shocks resampled from the
    stock's own standardized residuals, so fat tails come from real data (L7, L9).
    mu: drift of the log price per day (0 = no edge assumed)."""
    m = mean(std_resid)
    s = std(std_resid, 0)
    zs = [(z - m) / s for z in std_resid]  # exactly mean 0, variance 1
    def fn(rng, h):
        v = g["var_next"]
        for _ in range(h):
            z = zs[rng.randrange(len(zs))]
            r = math.sqrt(v) * z
            yield v, mu + r - 0.5 * v
            v = g["omega"] + g["alpha"] * r * r + g["beta"] * v
    return fn


def bootstrap_steps(rets, mu=0.0):
    def fn(rng, h):
        v = var(rets)
        for _ in range(h):
            yield v, mu + rets[rng.randrange(len(rets))]
    return fn


def ou_fit(x, dt=1.0):
    """Ornstein-Uhlenbeck dX = kappa (theta - X) dt + sigma dW, fitted through its exact AR(1) (L21)."""
    a = ar1(x)
    phi = a["phi"]
    if not 0 < phi < 1:
        return {"kappa": 0.0, "theta": a["level"], "sigma": a["sigma"], "half_life": float("inf"), "phi": phi}
    kappa = -math.log(phi) / dt
    sig = a["sigma"] * math.sqrt(2 * kappa / (1 - phi * phi))
    return {"kappa": kappa, "theta": a["level"], "sigma": sig, "half_life": math.log(2) / kappa,
            "phi": phi, "resid_sigma": a["sigma"]}


def ou_step(x, ou, dt, z):
    """Exact OU transition over dt."""
    e = math.exp(-ou["kappa"] * dt)
    sd = ou["sigma"] * math.sqrt((1 - e * e) / (2 * ou["kappa"])) if ou["kappa"] > 0 else ou["sigma"] * math.sqrt(dt)
    return ou["theta"] + (x - ou["theta"]) * e + sd * z


# ---------------------------------------------------------------------------
# portfolio (L14, L16)
# ---------------------------------------------------------------------------

def kelly_binary(p, b):
    """Kelly fraction for a bet that wins b per 1 risked with probability p (L16, L25)."""
    if b <= 0:
        return 0.0
    return p - (1 - p) / b


def project_capped_simplex(w, cap):
    """Closest weights (sum 1, 0 <= w <= cap) to w."""
    k = len(w)
    cap = max(cap, 1.0 / k)
    lo, hi = min(w) - cap, max(w)
    for _ in range(100):
        tau = (lo + hi) / 2
        s = sum(min(max(x - tau, 0), cap) for x in w)
        if s > 1:
            lo = tau
        else:
            hi = tau
    return [min(max(x - (lo + hi) / 2, 0), cap) for x in w]


def min_variance(S, cap=1.0, iters=3000):
    """Long-only minimum-variance weights with a per-asset cap (L14; Case Study 6 caps at 0.30)."""
    k = len(S)
    w = [1.0 / k] * k
    lr = 1.0 / max(max(abs(v) for row in S for v in row), 1e-12) / 4
    for _ in range(iters):
        g = matvec(S, w)
        w = project_capped_simplex([w[i] - lr * g[i] for i in range(k)], cap)
    return w


def mean_variance(S, mu, risk_aversion=4.0, cap=1.0, iters=4000):
    """Long-only Markowitz: maximize w'mu - (lambda/2) w'Sw, weights sum to 1 (L14)."""
    k = len(S)
    w = [1.0 / k] * k
    lr = 1.0 / max(risk_aversion * max(abs(v) for row in S for v in row), 1e-12) / 4
    for _ in range(iters):
        g = matvec(S, w)
        w = project_capped_simplex([w[i] + lr * (mu[i] - risk_aversion * g[i]) for i in range(k)], cap)
    return w


def risk_parity(S, iters=500):
    """Equal risk contribution weights (L16, the risk-parity portfolio)."""
    k = len(S)
    w = [1.0 / math.sqrt(S[i][i]) for i in range(k)]
    s = sum(w)
    w = [x / s for x in w]
    for _ in range(iters):
        Sw = matvec(S, w)
        port = dot(w, Sw)
        rc = [w[i] * Sw[i] for i in range(k)]
        target = port / k
        w = [w[i] * (target / rc[i]) ** 0.5 if rc[i] > 0 else w[i] for i in range(k)]
        s = sum(w)
        w = [x / s for x in w]
    return w


def risk_contributions(S, w):
    Sw = matvec(S, w)
    port = dot(w, Sw)
    return [w[i] * Sw[i] / port if port > 0 else 0.0 for i in range(len(w))]


# ---------------------------------------------------------------------------
# risk (L7)
# ---------------------------------------------------------------------------

def var_es(pnl, conf=0.99):
    """Historical VaR and expected shortfall, as positive losses."""
    losses = sorted(-x for x in pnl)
    q = quantile(losses, conf)
    tail = [l for l in losses if l >= q]
    return q, (mean(tail) if tail else q)


def kupiec(exceptions, n, conf=0.99):
    """Kupiec proportion-of-failures test: does the VaR break as often as promised?"""
    p = 1 - conf
    x = exceptions
    if n == 0:
        return float("nan"), float("nan")
    phat = x / n
    def ll(q):
        a = (n - x) * math.log(1 - q) if q < 1 else (0 if n == x else -1e300)
        b = x * math.log(q) if q > 0 else (0 if x == 0 else -1e300)
        return a + b
    lr = -2 * (ll(p) - ll(phat))
    return lr, chi2_sf(lr, 1)


# ---------------------------------------------------------------------------
# options (L18, L19, L20, L25)
# ---------------------------------------------------------------------------

def bs(S, K, T, r, sigma, kind="call", q=0.0):
    """Black-Scholes price and Greeks (L19). T in years; rates continuous."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0) if kind == "call" else max(K - S, 0)
        return {"price": intrinsic, "delta": float(intrinsic > 0) * (1 if kind == "call" else -1),
                "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0, "d1": float("nan"), "d2": float("nan"),
                "prob_itm": float(intrinsic > 0)}
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / sq
    d2 = d1 - sq
    dfq, dfr = math.exp(-q * T), math.exp(-r * T)
    if kind == "call":
        price = S * dfq * norm_cdf(d1) - K * dfr * norm_cdf(d2)
        delta = dfq * norm_cdf(d1)
        theta = (-S * dfq * norm_pdf(d1) * sigma / (2 * math.sqrt(T)) - r * K * dfr * norm_cdf(d2)
                 + q * S * dfq * norm_cdf(d1))
        rho = K * T * dfr * norm_cdf(d2)
        prob = norm_cdf(d2)
    else:
        price = K * dfr * norm_cdf(-d2) - S * dfq * norm_cdf(-d1)
        delta = -dfq * norm_cdf(-d1)
        theta = (-S * dfq * norm_pdf(d1) * sigma / (2 * math.sqrt(T)) + r * K * dfr * norm_cdf(-d2)
                 - q * S * dfq * norm_cdf(-d1))
        rho = -K * T * dfr * norm_cdf(-d2)
        prob = norm_cdf(-d2)
    return {"price": price, "delta": delta, "gamma": dfq * norm_pdf(d1) / (S * sq),
            "vega": S * dfq * norm_pdf(d1) * math.sqrt(T) / 100.0, "theta": theta / 365.0,
            "rho": rho / 100.0, "d1": d1, "d2": d2, "prob_itm": prob}


def implied_vol(price, S, K, T, r, kind="call", q=0.0):
    lo, hi = 1e-4, 5.0
    intrinsic = max(S * math.exp(-q * T) - K * math.exp(-r * T), 0) if kind == "call" else \
        max(K * math.exp(-r * T) - S * math.exp(-q * T), 0)
    if price < intrinsic - 1e-9 or price <= 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if bs(S, K, T, r, mid, kind, q)["price"] > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# execution (L22)
# ---------------------------------------------------------------------------

def almgren_chriss(X, T, N, sigma, eta, gamma=0.0, lam=1e-6):
    """Optimal liquidation trajectory (L22: calculus of variations for execution).

    Sell X shares over T (days) in N slices. sigma: daily price vol in $/share,
    eta: temporary impact ($ per share per share/day), lam: risk aversion.
    The Euler-Lagrange equation gives x(t) = X sinh(kappa (T - t)) / sinh(kappa T).
    """
    tau = T / float(N)
    et = eta - 0.5 * gamma * tau
    if et <= 0:
        et = eta
    kt2 = lam * sigma * sigma / et
    if kt2 < 1e-12:
        holdings = [X * (1 - j / float(N)) for j in range(N + 1)]
        kappa = 0.0
    else:
        kappa = math.acosh(0.5 * kt2 * tau * tau + 1) / tau
        holdings = [X * math.sinh(kappa * (T - j * tau)) / math.sinh(kappa * T) for j in range(N + 1)]
    trades = [holdings[j] - holdings[j + 1] for j in range(N)]
    cost = 0.5 * gamma * X * X + sum(eta / tau * n * n for n in trades)
    risk = sigma * sigma * tau * sum(h * h for h in holdings[1:])
    return {"holdings": holdings, "trades": trades, "kappa": kappa, "expected_cost": cost,
            "variance": risk, "tau": tau}


# ---------------------------------------------------------------------------
# market clock (New York)
# ---------------------------------------------------------------------------

NYSE_HOLIDAYS = {
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19",
    "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
}
NYSE_EARLY_CLOSE = {"2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26"}


def _nth_sunday(year, month, n):
    d = _dt.date(year, month, 1)
    d += _dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + _dt.timedelta(weeks=n - 1)


def ny_now(now=None):
    """New York wall-clock time, daylight saving included, without tz databases.

    now: None (the real clock) or "YYYY-MM-DD HH:MM" already in New York time.
    """
    if now:
        return _dt.datetime.strptime(now, "%Y-%m-%d %H:%M")
    utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    y = utc.year
    start = _dt.datetime.combine(_nth_sunday(y, 3, 2), _dt.time(7, 0))   # 2am EST = 7:00 UTC
    end = _dt.datetime.combine(_nth_sunday(y, 11, 1), _dt.time(6, 0))    # 2am EDT = 6:00 UTC
    off = -4 if start <= utc < end else -5
    return utc + _dt.timedelta(hours=off)


def market_session(ny):
    """(is_open, open_time, close_time, note) for US stocks at New York time `ny`."""
    day = ny.strftime("%Y-%m-%d")
    if ny.weekday() >= 5:
        return False, None, None, "weekend"
    if day in NYSE_HOLIDAYS:
        return False, None, None, "NYSE holiday"
    close = _dt.time(13, 0) if day in NYSE_EARLY_CLOSE else _dt.time(16, 0)
    o = _dt.time(9, 30)
    is_open = o <= ny.time() < close
    note = "early close 1:00 PM" if day in NYSE_EARLY_CLOSE else ""
    return is_open, o, close, note


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------

def money(x):
    if x is None or x != x:
        return "n/a"
    return ("-$" if x < 0 else "$") + "{:,.2f}".format(abs(x))


def pct(x, d=1):
    if x is None or x != x:
        return "n/a"
    return ("{:.%df}%%" % d).format(100 * x)


def num(x, d=2):
    if x is None or x != x:
        return "n/a"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return ("{:,.%df}" % d).format(x)


def price_str(x):
    """Prices as strings for broker JSON: cents for stocks, more for cheap coins."""
    if x >= 1:
        return "%.2f" % x
    return "%.6f" % x


def today_ny(now=None):
    return ny_now(now).strftime("%Y-%m-%d")
