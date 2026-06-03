# -*- coding: utf-8 -*-
# =============================================================================
# SCRIPT 2 - Mise a jour quotidienne automatique de BCASAD.CSV
# =============================================================================
# Prerequis : pip install casased pandas
# Utilisation : python 2_mise_a_jour_quotidienne.py
# Planification Windows (admin) :
#   schtasks /create /tn "BourseCasa" /tr "C:\Python\python.exe C:\python\2_mise_a_jour_quotidienne.py" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:00 /f
# =============================================================================

import csv, subprocess, sys, time, re, logging, warnings, io, os
warnings.filterwarnings("ignore")

# Rediriger stderr pour supprimer les warnings de casased
import contextlib

from datetime import date, datetime, timedelta
from pathlib import Path

DOSSIER  = Path(".")
CSV_PATH = DOSSIER / "BCASAD.CSV"
LOG_PATH = DOSSIER / "mise_a_jour.log"
CSV_COLS = ["Date", "Value", "Min", "Max", "Variation", "Volume", "Action", "index"]
SEP = "=" * 62

for p in ["casased", "pandas"]:
    try: __import__(p)
    except ImportError:
        subprocess.run([sys.executable,"-m","pip","install",p,"-q"],capture_output=True)

import casased as cas
import pandas as pd

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)
def ok(m):   log.info ("  [OK]  " + m)
def err(m):  log.error(" [ERR] " + m)
def warn(m): log.warning("[WAR] " + m)
def info(m): log.info ("  ...   " + m)

# ── Utilitaires ───────────────────────────────────────────────
def dernier_jour_ouvre():
    d = date.today()
    if d.weekday() == 5: d -= timedelta(days=1)
    if d.weekday() == 6: d -= timedelta(days=2)
    return d

def date_deja_presente(date_iso):
    if not CSV_PATH.exists(): return False
    with open(str(CSV_PATH), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("Date","").strip() == date_iso: return True
    return False

def to_f(val):
    try:
        s = str(val).strip().replace(",",".").replace("%","").replace(" ","")
        return float(s) if s not in ("","nan","None","-","NaN") else None
    except: return None

def to_i(val):
    try:
        s = re.sub(r"[^\d]","",str(val))
        return int(s) if s else 0
    except: return 0

def to_iso(v):
    if hasattr(v,"strftime"): return v.strftime("%Y-%m-%d")
    s = str(v)[:10]
    if "/" in s:
        p = s.split("/")
        if len(p)==3:
            if len(p[2])==4: return p[2]+"-"+p[1].zfill(2)+"-"+p[0].zfill(2)
            if len(p[0])==4: return p[0]+"-"+p[1].zfill(2)+"-"+p[2].zfill(2)
    return s

def trouver(df, *noms):
    cl = {c.lower():c for c in df.columns}
    for n in noms:
        if n.lower() in cl: return cl[n.lower()]
    for n in noms:
        for k,v in cl.items():
            if n.lower() in k: return v
    return None

def get_history_safe(action, debut, fin):
    """
    Appelle cas.get_history() en supprimant tous les warnings et stderr.
    Retourne un DataFrame ou None.
    """
    # Supprimer les warnings internes de casased
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            raw = cas.get_history(action, start=debut, end=fin)
    finally:
        sys.stderr = old_stderr

    if raw is None: return None

    # Convertir en DataFrame selon le type retourne
    if isinstance(raw, pd.DataFrame):
        df = raw.copy()
    elif isinstance(raw, dict):
        if not raw: return None
        try:
            # dict de listes -> DataFrame directement
            df = pd.DataFrame(raw)
        except Exception:
            try:
                # dict scalaire -> une seule ligne
                df = pd.DataFrame([raw])
            except Exception:
                return None
    elif isinstance(raw, list):
        if not raw: return None
        try:
            df = pd.DataFrame(raw)
        except Exception:
            return None
    else:
        return None

    if df.empty: return None

    # Remettre l index en colonnes si c est une date
    try:
        if df.index.name and any(k in str(df.index.name).lower() for k in ["date","time","seance"]):
            df = df.reset_index()
        elif hasattr(df.index, 'dtype') and str(df.index.dtype) in ['datetime64[ns]','object']:
            df = df.reset_index()
    except Exception:
        pass

    return df

# ── MAIN ──────────────────────────────────────────────────────
def main():
    print("\n" + SEP)
    print("  SCRIPT 2 - Mise a jour quotidienne")
    print(SEP)
    print("  Heure : " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    print("")

    # ── Trouver toutes les dates manquantes ──────────────────
    derniere_date_csv = None
    if CSV_PATH.exists():
        with open(str(CSV_PATH), encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ds = row.get("Date","").strip()
                if ds:
                    if derniere_date_csv is None or ds > derniere_date_csv:
                        derniere_date_csv = ds

    aujourd_hui = dernier_jour_ouvre()
    if derniere_date_csv:
        debut_manquant = datetime.strptime(derniere_date_csv, "%Y-%m-%d").date() + timedelta(days=1)
    else:
        debut_manquant = aujourd_hui

    dates_manquantes = []
    d_iter = debut_manquant
    while d_iter <= aujourd_hui:
        if d_iter.weekday() < 5:
            dates_manquantes.append(d_iter.strftime("%Y-%m-%d"))
        d_iter += timedelta(days=1)

    if not dates_manquantes:
        ok("CSV deja a jour jusqu au " + (derniere_date_csv or "?") + ". Rien a faire.")
        return

    info("Derniere date CSV : " + (derniere_date_csv or "aucune"))
    info(str(len(dates_manquantes)) + " seances manquantes : " + dates_manquantes[0] + " -> " + dates_manquantes[-1])

    date_debut_dl = dates_manquantes[0]
    date_fin_dl   = dates_manquantes[-1]

    if aujourd_hui == date.today() and datetime.now().hour < 16:
        warn("Bourse cloture a 15h30. Donnees du jour peut-etre incompletes.")

    # ── Recuperer la liste des actions ────────────────────────
    info("Recuperation de la liste des actions ...")
    try:
        actions = cas.notation()
        ok(str(len(actions)) + " actions trouvees.")
    except Exception as e:
        err("cas.notation() : " + str(e)); sys.exit(1)

    # ── Telecharger les donnees manquantes ────────────────────
    info("Telechargement : " + date_debut_dl + " -> " + date_fin_dl)
    print("")

    lignes_ecrites = 0
    actions_ok = 0
    actions_vides = 0

    with open(str(CSV_PATH), "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLS)

        for i, action in enumerate(actions, 1):
            pct = int(i / len(actions) * 100)
            sys.stdout.write("  [" + str(pct).rjust(3) + "%] " +
                           str(action)[:30].ljust(32) + " ... ")
            sys.stdout.flush()

            try:
                df = get_history_safe(action, date_debut_dl, date_fin_dl)

                if df is None:
                    sys.stdout.write("vide\n")
                    actions_vides += 1
                    time.sleep(0.3)
                    continue

                # Identifier les colonnes
                col_d   = trouver(df,"date","time","index","seance","day","timestamp")
                col_val = trouver(df,"close","last","cloture","cours","price","value","closing","adj close")
                col_min = trouver(df,"low","min","bas","lowest","intradaylow")
                col_max = trouver(df,"high","max","haut","highest","intradayhigh")
                col_var = trouver(df,"change","variation","var","pct","perf","hausse","evolution")
                col_vol = trouver(df,"volume","vol","shares","quantite","titres")

                if not col_val:
                    sys.stdout.write("col? " + str(list(df.columns)[:4]) + "\n")
                    actions_vides += 1
                    time.sleep(0.3)
                    continue

                # Ecrire chaque ligne
                count = 0
                for _, row in df.iterrows():
                    try:
                        val = to_f(row[col_val])
                        if val is None: continue

                        # Determiner la date de la ligne
                        if col_d:
                            d_iso = to_iso(row[col_d])
                        else:
                            d_iso = date_iso  # pas de colonne date -> date du jour

                        # Accepter uniquement les dates manquantes
                        if d_iso and len(d_iso)==10 and d_iso.startswith("20"):
                            if d_iso not in dates_manquantes:
                                continue  # date non manquante, on skip
                            date_a_ecrire = d_iso
                        else:
                            date_a_ecrire = date_fin_dl  # fallback

                        mn  = to_f(row[col_min]) if col_min else None
                        mx  = to_f(row[col_max]) if col_max else None
                        vr  = to_f(row[col_var]) if col_var else 0.0
                        vo  = to_i(row[col_vol]) if col_vol else 0

                        writer.writerow({
                            "Date":      date_a_ecrire,
                            "Value":     "{:.2f}".format(val),
                            "Min":       "{:.2f}".format(mn if mn is not None else val),
                            "Max":       "{:.2f}".format(mx if mx is not None else val),
                            "Variation": "{:.2f}".format(vr if vr is not None else 0.0),
                            "Volume":    str(vo),
                            "Action":    str(action).strip(),
                            "index":     "",
                        })
                        count += 1
                        lignes_ecrites += 1
                    except Exception:
                        pass

                if count > 0:
                    sys.stdout.write(str(count) + " ligne(s)\n")
                    actions_ok += 1
                else:
                    sys.stdout.write("0 ligne\n")
                    actions_vides += 1

            except Exception as e:
                sys.stdout.write("ERR: " + str(e)[:50] + "\n")
                actions_vides += 1

            time.sleep(0.4)

        # Ajouter lignes MASI et MSI20 pour chaque date manquante
        for dm in dates_manquantes:
            for nom_idx in ("MASI","MSI20"):
                writer.writerow({
                    "Date":"","Value":"","Min":"","Max":"",
                    "Variation":"","Volume":"",
                    "Action":nom_idx,"index":dm,
                })
                lignes_ecrites += 1

    print("")

    if lignes_ecrites <= 2:
        err("Aucune donnee ecrite dans le CSV (seulement MASI/MSI20 vides).")
        err("La bourse est peut-etre fermee ou les donnees ne sont pas disponibles.")
        sys.exit(1)

    ok(str(lignes_ecrites) + " lignes ajoutees dans BCASAD.CSV")

    # HTML regenere par le script 3 (etape suivante du workflow)

    # ── Rapport ───────────────────────────────────────────────
    print("")
    print(SEP)
    print("  RAPPORT " + date_debut_dl + " -> " + date_fin_dl)
    print(SEP)
    print("  Actions mises a jour : " + str(actions_ok))
    print("  Actions sans donnees : " + str(actions_vides))
    print("  Lignes CSV ajoutees  : " + str(lignes_ecrites))
    print(SEP + "\n")
    ok("Mise a jour terminee !")

if __name__ == "__main__":
    main()
