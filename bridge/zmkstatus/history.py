"""In-memory battery history and trend estimate per keyboard half."""

MAX_AGE_SECONDS = 24 * 3600
TREND_WINDOW_SECONDS = 6 * 3600
MIN_TREND_SPAN_SECONDS = 30 * 60
MIN_SAMPLE_INTERVAL = 5 * 60
SPARK_POINTS = 24


class BatteryHistory:
    def __init__(self, max_age=MAX_AGE_SECONDS, min_interval=MIN_SAMPLE_INTERVAL):
        self.max_age = max_age
        self.min_interval = min_interval
        self.samples = []  # [(timestamp_seconds, percent)], ascending
        self.seeded_from = None

    def seed(self, samples, source):
        rows = sorted(
            (float(t), int(round(p))) for t, p in samples if p is not None and 0 < p <= 100
        )
        if rows:
            self.samples = rows + [s for s in self.samples if s[0] > rows[-1][0]]
            self.seeded_from = source
        return len(rows)

    def add(self, now, percent):
        """Record a reading. Unchanged readings are kept at most every min_interval."""
        if percent is None:
            return False
        if self.samples:
            last_time, last_percent = self.samples[-1]
            if now < last_time:
                return False
            if last_percent == percent and now - last_time < self.min_interval:
                return False
        self.samples.append((float(now), int(percent)))
        cutoff = now - self.max_age
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.pop(0)
        return True

    def trend(self, now, window=TREND_WINDOW_SECONDS, min_span=MIN_TREND_SPAN_SECONDS):
        """Least-squares slope over the window, in percent per hour.

        perHour is None until the window spans at least min_span seconds with
        three or more samples, so a fresh start reports "collecting" rather
        than a misleading slope.
        """
        recent = [(t, p) for t, p in self.samples if t >= now - window]
        result = {
            "perHour": None,
            "spanMinutes": 0,
            "samples": len(recent),
            "points": downsample([p for _, p in self.samples if p is not None], SPARK_POINTS),
            "source": self.seeded_from or "memory",
        }
        if len(recent) < 2:
            return result
        span = recent[-1][0] - recent[0][0]
        result["spanMinutes"] = int(span // 60)
        if len(recent) < 3 or span < min_span:
            return result
        mean_t = sum(t for t, _ in recent) / len(recent)
        mean_p = sum(p for _, p in recent) / len(recent)
        denominator = sum((t - mean_t) ** 2 for t, _ in recent)
        if denominator <= 0:
            return result
        slope = sum((t - mean_t) * (p - mean_p) for t, p in recent) / denominator
        result["perHour"] = round(slope * 3600, 2)
        return result


def downsample(values, limit):
    if len(values) <= limit:
        return list(values)
    step = len(values) / float(limit)
    return [values[min(len(values) - 1, int(i * step))] for i in range(limit - 1)] + [values[-1]]
