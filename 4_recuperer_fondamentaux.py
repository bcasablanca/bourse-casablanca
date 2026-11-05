# -*- coding: utf-8 -*-
# =============================================================================
# SCRIPT 4 - Recuperation des donnees fondamentales  (v2 - API officielle BVC)
# =============================================================================
# Source : page Live Market de casablanca-bourse.com (via bvc.py) :
#   cours, variation, plus haut/bas, volume, capitalisation, NOMBRE DE TITRES,
#   secteur et statut pour les 81 valeurs cotees.
# Calcule ensuite depuis BCASAD.CSV : poids dans le marche, beta, liquidite,
# plus haut / plus bas 52 semaines, performance 1 an.
# Cours cibles analystes : via casased.notation_value() SI casased est
# installe et fonctionne (facultatif ; sinon le signal reste "N/A").
#
# A lancer APRES le script 2 (il utilise l'historique a jour) :
#   python 2_mise_a_jour_quotidienne.py
#   python 4_recuperer_fondamentaux.py
#   python 3_generer_html.py
#
# Prerequis : pip install requests certifi
# Sortie    : fondamentaux.json (dans le dossier du script)
# =============================================================================

import csv, io, json, subprocess, sys, warnings
warnings.filterwarnings("ignore")

for p in ["requests", "certifi"]:
    try: __import__(p)
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", p, "-q"], capture_output=True)

from collections import defaultdict
from datetime import datetime
import bvc

JSON_PATH = bvc.DOSSIER / "fondamentaux.json"
CSV_PATH  = bvc.CSV_PATH
SEP = "=" * 62

def fmt_mad(n):
    if n is None: return "N/A"
    if n >= 1e9:  return "{:.2f} Mrd MAD".format(n / 1e9)
    if n >= 1e6:  return "{:.2f} M MAD".format(n / 1e6)
    if n >= 1e3:  return "{:.1f} K MAD".format(n / 1e3)
    return "{:.2f} MAD".format(n)

# =============================================================================
# MARCHE DU JOUR (API officielle)
# =============================================================================
def recuperer_marche():
    print("  Lecture Live Market casablanca-bourse.com ...")
    m = bvc.marche_du_jour()
    donnees = {}
    for a in m["actions"]:
        if not a["cours"]:
            continue
        donnees[a["nom"]] = {
            "nom_bvc"       : a["emetteur"],
            "symbole"       : a["symbole"],
            "secteur"       : a["secteur"],
            "statut"        : a["statut"],
            "cours"         : a["cours"],
            "cours_ref"     : a["cours_ref"],
            "ouverture"     : a["ouverture"],
            "variation_jour": round(a["variation_jour"], 2) if a["variation_jour"] is not None else None,
            "haut_jour"     : a["haut_jour"],
            "bas_jour"      : a["bas_jour"],
            "volume_jour"   : a["volume_jour"],
            "capitalisation": a["capitalisation"],
            "nb_titres_bvc" : a["nb_titres"],
        }
    s = m["seance"]
    print("  [OK] " + str(len(donnees)) + " valeurs (seance " + s["statut"] + " du " + str(s["date"]) + ").")
    return donnees

# =============================================================================
# COURS CIBLES ANALYSTES (facultatif : casased)
# =============================================================================
def recuperer_cours_cibles():
    print("  Cours cibles analystes (casased, facultatif) ...")
    old = sys.stderr
    try:
        sys.stderr = io.StringIO()
        import casased as cas
        r = cas.notation_value() or {}
        sys.stderr = old
        print("  [OK] " + str(len(r)) + " cours cibles.")
        return r
    except Exception as e:
        sys.stderr = old
        print("  [--] indisponible (" + type(e).__name__ + ") : signaux analystes = N/A.")
        return {}

# =============================================================================
# HISTORIQUE CSV
# =============================================================================
def lire_historique():
    pa = defaultdict(list)
    if not CSV_PATH.exists(): return pa
    with open(str(CSV_PATH), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nom = row["Action"].strip()
            if nom in bvc.INDICES: continue
            ds = row["Date"].strip()
            if not ds: continue
            try:
                try:    vol = int(float(row.get("Volume", "0") or 0))
                except: vol = 0
                pa[nom].append({"date": ds, "close": float(row["Value"]),
                                "variation": float(row.get("Variation") or 0), "volume": vol})
            except Exception:
                pass
    for n in pa: pa[n].sort(key=lambda x: x["date"])
    return pa

# Indice de marche equipondere (coherent avec 3_generer_html.py)
def construire_proxy_marche(historique):
    par_date = defaultdict(list)
    for ss in historique.values():
        for s in ss:
            par_date[s["date"]].append(s["variation"])
    return {d: (sum(v) / len(v)) for d, v in par_date.items() if v}

def calc_beta(asset_ret, market_ret):
    pairs = [(a, m) for a, m in zip(asset_ret, market_ret) if a is not None and m is not None]
    if len(pairs) < 30: return None
    n = len(pairs)
    ma = sum(a for a, _ in pairs) / n; mm = sum(m for _, m in pairs) / n
    cov = sum((a - ma) * (m - mm) for a, m in pairs) / n
    var = sum((m - mm) ** 2 for _, m in pairs) / n
    return round(cov / var, 2) if var > 0 else None

def beta_action(hist, proxy):
    if len(hist) < 31: return None
    a_ret, m_ret = [], []
    for i in range(1, len(hist)):
        c0 = hist[i - 1]["close"]
        d = hist[i]["date"]
        if c0 and d in proxy:
            a_ret.append((hist[i]["close"] - c0) / c0 * 100); m_ret.append(proxy[d])
    return calc_beta(a_ret, m_ret)

def liquidite_moyenne(hist, n=60):
    """Valeur moyenne echangee par seance (cours x titres) en MAD."""
    derniers = hist[-n:]
    vals = [s["close"] * s["volume"] for s in derniers if s["volume"]]
    return round(sum(vals) / len(vals), 0) if vals else None

def haut_bas_52s(hist):
    if not hist: return (None, None)
    closes = [s["close"] for s in hist[-252:]]
    return (round(max(closes), 2), round(min(closes), 2))

# =============================================================================
# INDICATEURS
# =============================================================================
def interpreter_cible(nota_brut, cours):
    """notation_value() melange cours cibles, PER et valeurs aberrantes :
    cible acceptee si ratio cible/cours dans [0.40 ; 1.80], PER si 3..60."""
    cible = per = None
    if nota_brut is None or not cours:
        return cible, per
    try:
        nota = float(str(nota_brut).replace(" ", "").replace(",", "."))
    except ValueError:
        return cible, per
    if nota > 0:
        ratio = nota / cours
        if 0.40 <= ratio <= 1.80:
            cible = round(nota, 2)
        elif 3 <= nota <= 60 and ratio < 0.40:
            per = round(nota, 1)
    return cible, per

def calculer_indicateurs(marche, cours_cibles, historique):
    resultats = {}
    proxy = construire_proxy_marche(historique)
    cap_total = sum(d["capitalisation"] for d in marche.values() if d.get("capitalisation"))
    maj = datetime.now().strftime("%d/%m/%Y %H:%M")

    for nom, d in marche.items():
        cours, cap = d["cours"], d["capitalisation"]
        nb_titres = int(d["nb_titres_bvc"]) if d.get("nb_titres_bvc") else (int(cap / cours) if cap and cours else None)

        cible, per = interpreter_cible(cours_cibles.get(nom) or cours_cibles.get(d["nom_bvc"]), cours)
        potentiel = round((cible - cours) / cours * 100, 2) if cible else None
        if potentiel is not None and abs(potentiel) > 100:
            cible = potentiel = None

        signal = "N/A"
        if potentiel is not None:
            if potentiel > 15:    signal = "ACHAT FORT"
            elif potentiel > 5:   signal = "ACHAT"
            elif potentiel < -15: signal = "VENTE"
            elif potentiel < -5:  signal = "ALLEGEMENT"
            else:                 signal = "CONSERVER"
        elif per is not None:
            signal = "ACHAT" if per < 15 else ("CONSERVER" if per < 25 else "PRUDENCE")

        hist = historique.get(nom, [])
        perf_1an = None
        if len(hist) >= 250 and hist[-250]["close"]:
            perf_1an = round((hist[-1]["close"] - hist[-250]["close"]) / hist[-250]["close"] * 100, 2)
        haut_52s, bas_52s = haut_bas_52s(hist)
        d2 = {k: v for k, v in d.items() if k != "nb_titres_bvc"}

        resultats[nom] = {
            **d2,
            "nb_titres"    : nb_titres,
            "poids_marche" : round(cap / cap_total * 100, 2) if cap and cap_total else None,
            "beta"         : beta_action(hist, proxy),
            "liquidite"    : liquidite_moyenne(hist, 60) if hist else None,
            "haut_52s"     : haut_52s,
            "bas_52s"      : bas_52s,
            "cours_cible"  : cible,
            "per"          : per,
            "potentiel"    : potentiel,
            "signal_ana"   : signal,
            "perf_1an"     : perf_1an,
            "cap_fmt"      : fmt_mad(cap),
            "mise_a_jour"  : maj,
        }
    return resultats

# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + SEP)
    print("  SCRIPT 4 - Recuperation des fondamentaux (API officielle BVC)")
    print(SEP)
    print("  Heure : " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    print("")

    try:
        marche = recuperer_marche()
    except Exception as e:
        bvc.log("Script 4 : ECHEC lecture marche : " + str(e), "ERROR")
        print("  fondamentaux.json n'a pas ete modifie.")
        sys.exit(1)
    if not marche:
        bvc.log("Script 4 : aucune valeur recuperee, fondamentaux.json conserve.", "ERROR")
        sys.exit(1)

    cours_cibles = recuperer_cours_cibles()
    print("  Lecture historique CSV ...")
    historique = lire_historique()
    print("  [OK] " + str(len(historique)) + " valeurs dans le CSV.")
    sans_hist = sorted(n for n in marche if n not in historique)
    if sans_hist:
        print("  [..] Sans historique (valeurs suspendues, ou script 2 pas encore lance) : " + ", ".join(sans_hist))

    print("  Calcul des indicateurs ...")
    resultats = calculer_indicateurs(marche, cours_cibles, historique)

    tmp = JSON_PATH.with_suffix(".tmp")
    with open(str(tmp), "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    tmp.replace(JSON_PATH)

    print("")
    print(SEP)
    print("  BILAN : " + str(len(resultats)) + " valeurs -> " + str(JSON_PATH))
    print(SEP)
    print("  {:<20} {:>9} {:>7} {:>6} {:>6} {:>14} {:>9}".format(
          "Action", "Cours", "Var%", "Poids%", "Beta", "Liquidite/j", "Perf 1an"))
    print("  " + "-" * 76)
    top = sorted(resultats.items(), key=lambda kv: -(kv[1]["capitalisation"] or 0))[:10]
    for nom, r in top:
        f = lambda v, s="{:.2f}": s.format(v) if v is not None else "N/A"
        print("  {:<20} {:>9.2f} {:>7} {:>6} {:>6} {:>14} {:>9}".format(
              nom[:20], r["cours"], f(r["variation_jour"]), f(r["poids_marche"]), f(r["beta"]),
              fmt_mad(r["liquidite"]) if r["liquidite"] else "N/A", f(r["perf_1an"], "{:+.1f}%")))
    print(SEP + "\n")
    bvc.log("Script 4 OK : " + str(len(resultats)) + " valeurs dans fondamentaux.json")

if __name__ == "__main__":
    main()
