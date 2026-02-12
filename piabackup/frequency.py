# encoding: utf-8

def parse_frequency(freq_str):
    if not freq_str:
        raise Exception("Invalid frequency")
    s_freq = str(freq_str).strip()
    if s_freq.isdigit():
        return int(s_freq)
    import re
    
    if not re.fullmatch(r'(\s*\d+[wdhm]\s*)+', s_freq.lower()):
        raise Exception("Invalid frequency format. Use w, d, h, m (e.g. 1w 2d 30m).")

    total = 0
    # w=week, d=day, h=hour, m=minute
    matches = re.findall(r'(\d+)([wdhm])', s_freq.lower())
    for val, unit in matches:
        v = int(val)
        if unit == 'w': total += v * 7 * 86400
        elif unit == 'd': total += v * 86400
        elif unit == 'h': total += v * 3600
        elif unit == 'm': total += v * 60
    return total

def format_frequency(seconds):
    if not seconds: return ""
    s = int(seconds)
    parts = []
    w = s // (7 * 86400)
    if w > 0:
        parts.append(f"{w}w")
        s -= w * 7 * 86400
    d = s // 86400
    if d > 0:
        parts.append(f"{d}d")
        s -= d * 86400
    h = s // 3600
    if h > 0:
        parts.append(f"{h}h")
        s -= h * 3600
    m = s // 60
    if m > 0:
        parts.append(f"{m}m")
        s -= m * 60
    return "".join(parts)
