#!/usr/bin/env python3
"""
Sincroniza Garmin Connect + Hevy y escribe site/data.enc.json (CIFRADO con AES-GCM).

Uso:
  python sync.py --login   # una sola vez, en tu ordenador: guarda la sesión de Garmin
  python sync.py           # sincroniza (lo ejecuta GitHub Actions cada 30 min)

Variables de entorno (en GitHub: Settings > Secrets and variables > Actions):
  APP_PASSPHRASE   clave con la que se cifran los datos (la misma que escribes en el móvil)
  HEVY_API_KEY     clave de la API de Hevy (requiere Hevy Pro)
  GARMINTOKENS     (opcional) carpeta con la sesión de Garmin. Por defecto ~/.garminconnect
"""
import base64
import datetime as dt
import getpass
import hashlib
import io
import json
import os
import sys
import tarfile
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "site")
OUT = os.path.join(OUT_DIR, "data.enc.json")
TOKENS = os.path.expanduser(os.environ.get("GARMINTOKENS", "~/.garminconnect"))
TZ = ZoneInfo("Europe/Madrid")
ITER = 200_000

errors = []


def b64(x: bytes) -> str:
    return base64.b64encode(x).decode()


def encrypt(obj, passphrase: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, ITER, 32)
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, separators=(",", ":")).encode(), None)
    return {"v": 1, "iter": ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def safe(name, fn):
    """Ejecuta fn; si falla, lo anota y devuelve None (el resto de datos sigue)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        errors.append(f"{name}: {type(e).__name__} {str(e)[:100]}")
        return None


def today():
    return dt.datetime.now(TZ).date()


def days_back(n):
    t = today()
    return [(t - dt.timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def fmt_time(sec):
    sec = int(round(sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ───────────────────────── Garmin ─────────────────────────
def copy_to_clipboard(text: str) -> bool:
    import platform
    import subprocess

    cmds = [["clip"]] if platform.system() == "Windows" else [["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]]
    for c in cmds:
        try:
            subprocess.run(c, input=text.encode("ascii"), check=True)
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def garmin_login_interactive():
    from garminconnect import Garmin

    try:
        Garmin().login(TOKENS)  # si ya hay una sesión guardada, se reutiliza sin pedir nada
        print("Ya había una sesión de Garmin guardada: la reutilizo.")
    except Exception:  # noqa: BLE001
        email = input("Email de Garmin Connect: ").strip()
        pwd = getpass.getpass("Contraseña (no se ve al escribir): ")
        Garmin(email, pwd, prompt_mfa=lambda: input("Código de verificación (MFA): ").strip()).login(TOKENS)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(TOKENS, arcname=".garminconnect")
    token = b64(buf.getvalue())
    # Se guarda en tu carpeta personal, NUNCA junto al código (para que no se suba a GitHub por error)
    path = os.path.join(os.path.expanduser("~"), "garmin_tokens_b64.txt")
    with open(path, "w") as f:
        f.write(token)
    os.chmod(path, 0o600)
    if copy_to_clipboard(token):
        print("\nListo. El texto ya está COPIADO en el portapapeles: pégalo en el secreto GARMIN_TOKENS_B64 de GitHub.")
    else:
        print(f"\nListo. Abre {path}, copia todo su contenido y pégalo en el secreto GARMIN_TOKENS_B64 de GitHub.")
    print(f"(Copia de seguridad en {path}. Es como una contraseña: no la subas a ningún sitio.)")


def garmin_client():
    from garminconnect import Garmin

    g = Garmin()
    g.login(TOKENS)
    return g


def g_stats(g):
    d = g.get_stats(today().isoformat()) or {}
    return {
        "date": today().isoformat(),
        "total_steps": d.get("totalSteps"),
        "resting_heart_rate_bpm": d.get("restingHeartRate"),
        "last_7_days_avg_resting_hr": d.get("lastSevenDaysAvgRestingHeartRate"),
        "avg_stress_level": d.get("averageStressLevel"),
        "body_battery_highest": d.get("bodyBatteryHighestValue"),
        "body_battery_lowest": d.get("bodyBatteryLowestValue"),
        "body_battery_current": d.get("bodyBatteryMostRecentValue"),
        "avg_spo2_percent": d.get("averageSpo2"),
    }


def g_readiness(g):
    arr = g.get_training_readiness(today().isoformat()) or []
    if isinstance(arr, dict):
        arr = [arr]
    if not arr:
        return None
    pick = next((x for x in arr if x.get("context") == "AFTER_WAKEUP_RESET"), arr[0])
    return [{
        "date": pick.get("calendarDate") or today().isoformat(),
        "level": pick.get("level"),
        "score": pick.get("score"),
        "feedback": pick.get("feedbackShort"),
        "sleep_factor_percent": pick.get("sleepScoreFactorPercent"),
        "recovery_factor_percent": pick.get("recoveryTimeFactorPercent"),
        "training_load_factor_percent": pick.get("acwrFactorPercent"),
        "hrv_factor_percent": pick.get("hrvFactorPercent"),
        "stress_history_factor_percent": pick.get("stressHistoryFactorPercent"),
        "sleep_history_factor_percent": pick.get("sleepHistoryFactorPercent"),
        "hrv_weekly_avg": pick.get("hrvWeeklyAverage"),
        "acute_load": pick.get("acuteLoad"),
    }]


def g_sleep(g):
    nights = []
    for d in days_back(14):
        try:
            raw = g.get_sleep_data(d) or {}
        except Exception:  # noche sin datos
            continue
        s = raw.get("dailySleepDTO") or {}
        if not s.get("sleepTimeSeconds"):
            continue
        score = ((s.get("sleepScores") or {}).get("overall") or {}).get("value")
        nights.append({
            "date": s.get("calendarDate") or d,
            "sleep_start": s.get("sleepStartTimestampGMT"),
            "sleep_score": score,
            "sleep_hours": round(s["sleepTimeSeconds"] / 3600, 2),
            "deep_sleep_seconds": s.get("deepSleepSeconds"),
            "light_sleep_seconds": s.get("lightSleepSeconds"),
            "rem_sleep_seconds": s.get("remSleepSeconds"),
            "awake_seconds": s.get("awakeSleepSeconds"),
            "resting_heart_rate_bpm": raw.get("restingHeartRate"),
            "avg_overnight_hrv": raw.get("avgOvernightHrv"),
        })
    return {"nights": nights}


def g_hrv(g):
    trend = []
    for d in days_back(15):
        try:
            s = (g.get_hrv_data(d) or {}).get("hrvSummary") or {}
        except Exception:
            continue
        if s.get("lastNightAvg") is None:
            continue
        trend.append({"date": d, "last_night_avg_hrv_ms": s.get("lastNightAvg"), "weekly_avg_hrv_ms": s.get("weeklyAvg")})
    return {"trend": trend}


def g_acts(g):
    out = []
    for a in g.get_activities(0, 80) or []:
        out.append({
            "id": a.get("activityId"),
            "name": a.get("activityName"),
            "type": (a.get("activityType") or {}).get("typeKey"),
            "start_time": a.get("startTimeLocal"),
            "distance_meters": a.get("distance"),
            "duration_seconds": a.get("duration"),
            "avg_hr_bpm": a.get("averageHR"),
            "max_hr_bpm": a.get("maxHR"),
            "calories": a.get("calories"),
            "elevation_gain_m": a.get("elevationGain"),
            "aerobic_te": a.get("aerobicTrainingEffect"),
            "anaerobic_te": a.get("anaerobicTrainingEffect"),
            "training_load": a.get("activityTrainingLoad"),
            "avg_cadence": a.get("averageRunningCadenceInStepsPerMinute"),
            "steps": a.get("steps"),
        })
    return {"activities": out}


def g_rundet(g, acts):
    """Vueltas y tiempo por zona de FC de las carreras de los últimos 21 días (máx. 12)."""
    import time

    if not acts:
        return None
    limit = (today() - dt.timedelta(days=21)).isoformat()
    runs = [a for a in acts.get("activities", [])
            if "run" in (a.get("type") or "") and (a.get("start_time") or "")[:10] >= limit][:12]
    det = {}
    for a in runs:
        aid, item = a["id"], {}
        try:
            sp = g.get_activity_splits(aid) or {}
            laps = []
            for l in sp.get("lapDTOs") or []:
                if not l.get("distance") or not l.get("duration"):
                    continue
                laps.append({
                    "d": round(l["distance"], 1),
                    "t": round(l["duration"], 1),
                    "hr": l.get("averageHR"),
                    "mx": l.get("maxHR"),
                    "k": l.get("intensityType"),
                })
            if laps:
                item["laps"] = laps
        except Exception as e:  # noqa: BLE001
            errors.append(f"rundet-splits {aid}: {type(e).__name__}")
        try:
            zs = g.get_activity_hr_in_timezones(aid) or []
            zz = [{"z": z.get("zoneNumber"), "s": round(z.get("secsInZone") or 0)} for z in zs if z.get("zoneNumber")]
            if zz:
                item["zones"] = zz
        except Exception as e:  # noqa: BLE001
            errors.append(f"rundet-zones {aid}: {type(e).__name__}")
        if item:
            det[str(aid)] = item
        time.sleep(0.4)  # trato amable con la API de Garmin
    return {"by_id": det}


def g_vo2(g):
    trend, last = [], None
    ds = days_back(42)
    for k, d in enumerate(ds):
        if k % 2 and k != len(ds) - 1:  # el VO2máx cambia poco: un día sí y otro no, y siempre el último
            continue
        try:
            m = g.get_max_metrics(d) or []
        except Exception:
            continue
        v = None
        if m:
            v = ((m[0] or {}).get("generic") or {}).get("vo2MaxPreciseValue")
        if v is not None and v != last:
            trend.append({"date": d, "vo2_max": round(float(v), 1)})
            last = v
    return {"trend": trend}


def g_pred(g):
    p = g.get_race_predictions() or {}
    if isinstance(p, list):
        p = p[0] if p else {}
    keys = {"5K": "time5K", "10K": "time10K", "half_marathon": "timeHalfMarathon", "marathon": "timeMarathon"}
    out = {}
    for k, src in keys.items():
        if p.get(src):
            out[k] = {"time": fmt_time(p[src]), "time_seconds": p[src]}
    return {"predictions": out} if out else None


def g_status(g):
    raw = g.get_training_status(today().isoformat()) or {}
    latest = ((raw.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")) or {}
    d = next(iter(latest.values()), {}) if latest else {}
    acute = d.get("acuteTrainingLoadDTO") or {}
    vo2 = ((raw.get("mostRecentVO2Max") or {}).get("generic") or {}).get("vo2MaxPreciseValue")
    return {
        "training_status_feedback": d.get("trainingStatusFeedbackPhrase"),
        "acute_load": acute.get("dailyTrainingLoadAcute"),
        "chronic_load": acute.get("dailyTrainingLoadChronic"),
        "load_ratio": acute.get("dailyAcuteChronicWorkloadRatio"),
        "acwr_status": acute.get("acwrStatus"),
        "optimal_chronic_load_min": acute.get("minTrainingLoadChronic"),
        "optimal_chronic_load_max": acute.get("maxTrainingLoadChronic"),
        "vo2_max_precise": vo2,
    }


def g_weight(g):
    start = (today() - dt.timedelta(days=34)).isoformat()
    raw = g.get_weigh_ins(start, today().isoformat()) or {}
    out = []
    for s in raw.get("dailyWeightSummaries") or []:
        w = (s.get("latestWeight") or {}).get("weight")
        if w:
            out.append({"date": s.get("summaryDate"), "weight_kg": round(w / 1000, 1)})
    return {"measurements": out}


# ───────────────────────── Hevy ─────────────────────────
def hevy():
    import requests

    key = os.environ.get("HEVY_API_KEY")
    if not key:
        raise RuntimeError("falta HEVY_API_KEY")
    workouts, page = [], 1
    while page <= 6:
        r = requests.get(
            "https://api.hevyapp.com/v1/workouts",
            params={"page": page, "pageSize": 10},
            headers={"api-key": key},
            timeout=30,
        )
        r.raise_for_status()
        j = r.json()
        for w in j.get("workouts", []):
            ex = [{
                "title": e.get("title"),
                "notes": e.get("notes") or None,
                "sets": [{"type": s.get("type"), "weight_kg": s.get("weight_kg"), "reps": s.get("reps"), "rpe": s.get("rpe")} for s in e.get("sets", [])],
            } for e in w.get("exercises", [])]
            workouts.append({
                "id": w.get("id"), "title": w.get("title"),
                "start_time": w.get("start_time"), "end_time": w.get("end_time"),
                "description": w.get("description") or None,
                "exercise_count": len(ex), "set_count": sum(len(e["sets"]) for e in ex),
                "exercises": ex,
            })
        if page >= j.get("page_count", 1):
            break
        page += 1
    return {"workouts": workouts}


def main():
    if "--login" in sys.argv:
        garmin_login_interactive()
        return
    pw = os.environ.get("APP_PASSPHRASE")
    if not pw:
        sys.exit("Falta APP_PASSPHRASE: no escribo datos sin cifrar.")
    data = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    g = safe("garmin-login", garmin_client)
    if g:
        for key, fn in [("stats", g_stats), ("readiness", g_readiness), ("sleep", g_sleep), ("hrv", g_hrv),
                        ("acts", g_acts), ("vo2", g_vo2), ("pred", g_pred), ("status", g_status), ("weight", g_weight)]:
            data[key] = safe(key, lambda fn=fn: fn(g))
        data["rundet"] = safe("rundet", lambda: g_rundet(g, data.get("acts")))
    data["hevy"] = safe("hevy", hevy)
    data["errors"] = errors
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(encrypt(data, pw), f)
    print("OK" if not errors else "Terminado con avisos:\n  " + "\n  ".join(errors))


if __name__ == "__main__":
    main()
