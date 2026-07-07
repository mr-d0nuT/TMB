#!/usr/bin/env python3
"""Genera hispano-igualadina.json a partir del GTFS oficial de buses
interurbanos de la Generalitat (analisi.transparenciacatalunya.cat).

Formato compacto para la app:
{
  "v": "YYYY-MM-DD",
  "lines": [[short, long], ...],
  "heads": ["destino", ...],
  "stops": [[stop_id, nombre, lat, lon], ...],
  "dates": {"YYYYMMDD": [svcIdx, ...], ...},          # 30 días vista
  "deps":  {stopIdx: [[lineIdx, svcIdx, depMin, headIdx, arrEndMin], ...]}
}
Los minutos son desde medianoche del día de servicio (pueden superar 1440).
"""
import csv, io, json, sys, zipfile, urllib.request, collections
from datetime import date, timedelta

GTFS_URL = "https://analisi.transparenciacatalunya.cat/download/bca2-b4i3/application/zip"
AGENCY_MATCH = "igualadina"
DAYS_AHEAD = 30
OUT = "hispano-igualadina.json"


def main():
    print("Descargando GTFS…", file=sys.stderr)
    raw = urllib.request.urlopen(GTFS_URL, timeout=300).read()
    zf = zipfile.ZipFile(io.BytesIO(raw))

    def rows(name):
        with zf.open(name) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                yield {(k or "").strip(): (v or "").strip() for k, v in r.items()}

    agency_ids = {a["agency_id"] for a in rows("agency.txt")
                  if AGENCY_MATCH in a["agency_name"].lower()}
    if not agency_ids:
        sys.exit("Agencia no encontrada en el GTFS")

    routes = {r["route_id"]: (r["route_short_name"], r["route_long_name"])
              for r in rows("routes.txt") if r["agency_id"] in agency_ids}
    lines, line_idx = [], {}
    for rid, (short, long_) in sorted(routes.items()):
        line_idx[rid] = len(lines)
        lines.append([short, long_])

    trips = {t["trip_id"]: t for t in rows("trips.txt") if t["route_id"] in routes}

    # calendario → fechas concretas activas (hoy + 30 días)
    today = date.today()
    horizon = {today + timedelta(d) for d in range(DAYS_AHEAD)}
    svc_dates = collections.defaultdict(set)
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for c in rows("calendar.txt"):
        d0 = date(int(c["start_date"][:4]), int(c["start_date"][4:6]), int(c["start_date"][6:]))
        d1 = date(int(c["end_date"][:4]), int(c["end_date"][4:6]), int(c["end_date"][6:]))
        for d in horizon:
            if d0 <= d <= d1 and c[weekdays[d.weekday()]] == "1":
                svc_dates[c["service_id"]].add(d)
    for c in rows("calendar_dates.txt"):
        d = date(int(c["date"][:4]), int(c["date"][4:6]), int(c["date"][6:]))
        if d in horizon:
            if c["exception_type"] == "1":
                svc_dates[c["service_id"]].add(d)
            else:
                svc_dates[c["service_id"]].discard(d)

    services = sorted({t["service_id"] for t in trips.values()} & set(svc_dates))
    svc_idx = {s: i for i, s in enumerate(services)}
    dates = collections.defaultdict(list)
    for s in services:
        for d in svc_dates[s]:
            dates[d.strftime("%Y%m%d")].append(svc_idx[s])

    def to_min(hms):
        # GTFS permite horas vacías en paradas sin timepoint y formatos H:MM
        parts = (hms or "").split(":")
        if len(parts) < 2 or not parts[0].strip().isdigit():
            return None
        return int(parts[0]) * 60 + int(parts[1])

    # stop_times por trip
    trip_stops = collections.defaultdict(list)
    for st in rows("stop_times.txt"):
        if st["trip_id"] in trips:
            trip_stops[st["trip_id"]].append(
                (int(st["stop_sequence"]), st["stop_id"], to_min(st["departure_time"]), to_min(st["arrival_time"])))

    stops_meta = {s["stop_id"]: (s["stop_name"], round(float(s["stop_lat"]), 5), round(float(s["stop_lon"]), 5))
                  for s in rows("stops.txt")}

    heads, head_idx = [], {}
    stops, stop_idx = [], {}
    deps = collections.defaultdict(list)

    for tid, seq in trip_stops.items():
        t = trips[tid]
        if t["service_id"] not in svc_idx:
            continue
        seq.sort()
        last_arr = next((x[3] for x in reversed(seq) if x[3] is not None), None)
        if last_arr is None:
            continue
        head = t.get("trip_headsign") or stops_meta.get(seq[-1][1], ("?",))[0]
        if head not in head_idx:
            head_idx[head] = len(heads)
            heads.append(head)
        li = line_idx[t["route_id"]]
        si_svc = svc_idx[t["service_id"]]
        for _, sid, dep, _arr in seq[:-1]:  # en la última parada ya no se sube
            if sid not in stops_meta or dep is None:
                continue
            if sid not in stop_idx:
                stop_idx[sid] = len(stops)
                name, lat, lon = stops_meta[sid]
                stops.append([sid, name, lat, lon])
            deps[stop_idx[sid]].append([li, si_svc, dep, head_idx[head], last_arr])

    for v in deps.values():
        v.sort(key=lambda x: x[2])

    out = {"v": today.isoformat(), "lines": lines, "heads": heads,
           "stops": stops, "dates": dates, "deps": deps}
    data = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(data)
    print(f"{OUT}: {len(data)} bytes · {len(stops)} paradas · {len(lines)} líneas · "
          f"{sum(len(v) for v in deps.values())} salidas", file=sys.stderr)


if __name__ == "__main__":
    main()
