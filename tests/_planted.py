"""A synthetic market with a planted edge: after a 10-day z-score of -2, prices drift up for 5 days."""
import json, math, random, datetime as dt, sys
def make(path, n_sym=30, n_days=2000, seed=7):
    rng = random.Random(seed)
    d0 = dt.date(2019, 1, 1); dates = []
    d = d0
    while len(dates) < n_days:
        if d.weekday() < 5: dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    out = {}
    for k in range(n_sym):
        lp = [math.log(100)]; boost = 0
        for i in range(1, n_days):
            w = lp[-10:]
            if len(w) == 10:
                m = sum(w) / 10; sd = (sum((x - m) ** 2 for x in w) / 9) ** 0.5
                if sd > 0 and (lp[-1] - m) / sd <= -2: boost = 5
            mu = 0.006 if boost > 0 else 0.0
            boost = max(boost - 1, 0)
            lp.append(lp[-1] + mu + rng.gauss(0, 0.02))
        # end on a dip so today's signal fires
        for j in range(4): lp[-4 + j] = lp[-5] - 0.03 * (j + 1)
        out["Q" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[k % 26] + ("" if k < 26 else "X")] = {"dates": dates, "close": [round(math.exp(x), 4) for x in lp]}
    json.dump(out, open(path, "w"))
    return dates[-1]
if __name__ == "__main__":
    print(make(sys.argv[1]))
