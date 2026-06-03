# -*- coding: utf-8 -*-
# =============================================================================
# SCRIPT 4 - Recuperation des donnees fondamentales
# =============================================================================
# Scrape casablanca-bourse.com pour recuperer :
#   - Cours, Capitalisation, Volume (temps reel)
#   - Cours cible analystes (via casased.notation_value)
#   - Calcul BPA estime = Capitalisation / (NombreTitres * PER estime)
#
# Prerequis : pip install casased requests beautifulsoup4 lxml pandas
# Utilisation : python 4_recuperer_fondamentaux.py
# Sortie : C:\python\fondamentaux.json
# =============================================================================

import csv, json, subprocess, sys, warnings, io, re, time
warnings.filterwarnings("ignore")

for p in ["casased","requests","beautifulsoup4","lxml","pandas"]:
    try: __import__(p.replace("-","_").split(".")[0])
    except: subprocess.run([sys.executable,"-m","pip","install",p,"-q"],capture_output=True)

import requests
from bs4 import BeautifulSoup
import pandas as pd
import casased as cas
import urllib3
urllib3.disable_warnings()
from datetime import datetime
from pathlib import Path

DOSSIER   = Path(r"C:\python")
JSON_PATH = DOSSIER / "fondamentaux.json"
CSV_PATH  = DOSSIER / "BCASAD.CSV"
SEP = "=" * 62

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
BASE = "https://www.casablanca-bourse.com"

# =============================================================================
# UTILITAIRES
# =============================================================================
def to_float(s):
    try:
        return float(str(s).replace(" ","").replace("\xa0","").replace(",",".").replace("%",""))
    except: return None

def to_int(s):
    try: return int(re.sub(r"[^\d]","",str(s)))
    except: return 0

def fmt_mad(n):
    if n is None: return "N/A"
    if n >= 1e9:  return "{:.2f} Mrd MAD".format(n/1e9)
    if n >= 1e6:  return "{:.2f} M MAD".format(n/1e6)
    if n >= 1e3:  return "{:.1f} K MAD".format(n/1e3)
    return "{:.2f} MAD".format(n)

# =============================================================================
# CORRESPONDANCE noms BVC -> noms CSV
# =============================================================================
NOM_BVC_TO_CSV = {
    "ATTIJARIWAFA BANK"            : "Attijariwafa",
    "BANQUE CENTRALE POPULAIRE"    : "BCP",
    "BANK OF AFRICA"               : "BOA",
    "BMCI"                         : "BMCI",
    "CREDIT DU MAROC"              : "CDM",
    "CFG BANK"                     : "CFG Bank",
    "CIH"                          : "CIH",
    "COSUMAR"                      : "COSUMAR",
    "CIMENTS DU MAROC"             : "Ciments Maroc",
    "LAFARGEHOLCIM MAROC"          : "LafargeHolcim",
    "AFRIQUIA GAZ"                 : "Afriquia Gaz",
    "TOTALENERGIES MARKETING MAROC": "Total Maroc",
    "LESIEUR CRISTAL"              : "Lesieur Cristal",
    "SODEP-Marsa Maroc"            : "Marsa Maroc",
    "SOCIETE DES BOISSONS DU MAROC": "Ste Boissons",
    "WAFA ASSURANCE"               : "Wafa Assur",
    "ATLANTASANAD"                 : "ATLANTASANAD",
    "AKDITAL"                      : "Akdital",
    "SOTHEMA"                      : "SOTHEMA",
    "PROMOPHARM S.A."              : "PROMOPHARM",
    "SMI"                          : "SMI",
    "MINIERE TOUISSIT"             : "CMT",
    "MANAGEM"                      : "Managem",
    "DOUJA PROM ADDOHA"            : "Addoha",
    "ARADEI CAPITAL"               : "Aradei Capital",
    "ALUMINIUM DU MAROC"           : "Aluminium Maroc",
    "COLORADO"                     : "Colorado",
    "DARI COUSPATE"                : "Dari Couspate",
    "DELATTRE LEVIVIER MAROC"      : "DELATTRE LEVIVIER MAROC",
    "DELTA HOLDING"                : "Delta Holding",
    "DIAC SALAF"                   : "DIAC Salaf",
    "DISTY TECHNOLOGIES"           : "Disty Technolog",
    "DISWAY"                       : "DISWAY",
    "M2M Group"                    : "M2M Group",
    "MICRODATA"                    : "Microdata",
    "CTM"                          : "CTM",
    "MUTANDIS SCA"                 : "Mutandis",
    "OULMES"                       : "Oulmes",
    "REBAB COMPANY"                : "Rebab Company",
    "RISMA"                        : "Risma",
    "S.M MONETIQUE"                : "S2M",
    "SALAFIN"                      : "SALAFIN",
    "SONASID"                      : "Sonasid",
    "SNEP"                         : "SNEP",
    "STROC INDUSTRIE"              : "STROC Indus",
    "TAQA MOROCCO"                 : "TAQA Morocco",
    "TGCC S.A"                     : "TGCC",
    "TIMAR"                        : "Timar",
    "UNIMER"                       : "Unimer",
    "ZELLIDJA S.A"                 : "Zellidja",
    "STOKVIS NORD AFRIQUE"         : "Stokvis Nord Afr",
    "SGTM S.A"                     : "SGTM",
    "JET CONTRACTORS"              : "Jet Contractors",
    "IB MAROC.COM"                 : "IBMaroc",
    "INVOLYS"                      : "INVOLYS",
    "IMMORENTE INVEST"             : "Immr Invest",
    "EQDOM"                        : "EQDOM",
    "ENNAKL"                       : "Ennakl",
    "FENIE BROSSETTE"              : "FENIE BROSSETTE",
    "AUTO HALL"                    : "Auto Hall",
    "AUTO NEJMA"                   : "Auto Nejma",
    "BALIMA"                       : "BALIMA",
    "CMGP GROUP"                   : "CMGP Group",
    "CASH PLUS S.A"                : "Cash Plus",
    "CARTIER SAADA"                : "Cartier Saada",
    "MAGHREBAIL"                   : "SALAFIN",
    "AGMA"                         : "Agma",
    "AFMA"                         : "AFMA",
    "AFRIC INDUSTRIES SA"          : "Afric Indus",
    "ALLIANCES"                    : "Alliances",
    "RESIDENCES DAR SAADA"         : "Res.Dar Saada",
    "SANLAM MAROC"                 : "Sanlam Maroc",
    "ITISSALAT AL-MAGHRIB"         : "IAM",
    "LABEL VIE"                    : "LABEL VIE",
    "HPS"                          : "HPS",
    "VICENNE"                      : "Akdital",
    "MED PAPER"                    : "MED PAPER",
    "MAGHREB OXYGENE"              : "Maghreb Oxygene",
    "MAROC LEASING"                : "Maroc Leasing",
    "REALISATIONS MECANIQUES"      : "Rebab Company",
}

def nom_csv(nom_bvc):
    if nom_bvc in NOM_BVC_TO_CSV:
        return NOM_BVC_TO_CSV[nom_bvc]
    # Recherche partielle
    n = nom_bvc.upper()
    for k, v in NOM_BVC_TO_CSV.items():
        if k.upper() in n or n in k.upper():
            return v
    return nom_bvc

# =============================================================================
# SCRAPING casablanca-bourse.com
# =============================================================================
def scraper_marche():
    print("  Scraping casablanca-bourse.com ...")
    try:
        r = requests.get(
            BASE + "/fr/live-market/marche-actions-groupement",
            headers=HEADERS, timeout=15, verify=False
        )
        r.raise_for_status()
    except Exception as e:
        print("  ERREUR scraping : " + str(e))
        return {}

    soup = BeautifulSoup(r.text, "lxml")
    tables = soup.find_all("table")
    donnees = {}

    # Colonnes attendues
    COL = {
        "instrument": 0,
        "statut": 1,
        "cours_ref": 2,
        "ouverture": 3,
        "dernier_cours": 4,
        "qte_echangee": 5,
        "volume": 6,
        "variation": 7,
        "haut_jour": 8,
        "bas_jour": 9,
        "capitalisation": 14,
        "nb_transactions": 15,
    }

    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td","th"])]
            if len(cells) < 15: continue
            if cells[0] in ("Instrument", ""): continue

            nom_bvc = cells[0].strip()
            nom_c   = nom_csv(nom_bvc)

            cours   = to_float(cells[4]) or to_float(cells[2])  # dernier cours ou cours ref
            cap     = to_float(cells[14])
            var     = to_float(cells[7])
            vol     = to_float(cells[6])
            haut    = to_float(cells[8])
            bas     = to_float(cells[9])
            statut  = cells[1]

            if not cours: continue

            donnees[nom_c] = {
                "nom_bvc"       : nom_bvc,
                "statut"        : statut,
                "cours"         : cours,
                "cours_ref"     : to_float(cells[2]),
                "ouverture"     : to_float(cells[3]),
                "variation_jour": var,
                "haut_jour"     : haut,
                "bas_jour"      : bas,
                "volume_jour"   : vol,
                "capitalisation": cap,
            }

    print("  [OK] " + str(len(donnees)) + " actions scrapees.")
    return donnees

# =============================================================================
# COURS CIBLES ANALYSTES (casased)
# =============================================================================
def recuperer_cours_cibles():
    print("  Recuperation cours cibles analystes ...")
    try:
        old = sys.stderr; sys.stderr = io.StringIO()
        r = cas.notation_value()
        sys.stderr = old
        print("  [OK] " + str(len(r)) + " cours cibles.")
        return r
    except Exception as e:
        sys.stderr = old
        print("  ERREUR notation_value : " + str(e))
        return {}

# =============================================================================
# CALCUL DES INDICATEURS DERIVES
# =============================================================================
def calculer_indicateurs(donnees_marche, cours_cibles, historique_csv):
    """
    Calcule les indicateurs fondamentaux derives :
    - Nombre de titres = Capitalisation / Cours
    - Poids dans la capitalisation totale du marche
    - Beta vs indice equipondere (coherent avec 3_generer_html.py)
    - Liquidite moyenne quotidienne (MAD)
    - Fourchette 52 semaines
    - Cours cible analystes (depuis notation_value, interprete prudemment)
    - Potentiel = (Cours cible - Cours) / Cours * 100
    """
    resultats = {}

    # Indice de marche equipondere + capitalisation totale du marche
    proxy = construire_proxy_marche(historique_csv)
    cap_total = sum(d["capitalisation"] for d in donnees_marche.values()
                    if d.get("capitalisation"))

    for nom, d in donnees_marche.items():
        cours = d["cours"]
        cap   = d["capitalisation"]

        # Nombre de titres
        nb_titres = int(cap / cours) if cours and cap else None

        # Interpretation prudente de notation_value() :
        # La fonction retourne un melange heterogene (cours cibles, PER, parfois
        # des valeurs aberrantes). On n accepte une valeur comme COURS CIBLE que
        # si le potentiel implicite reste plausible (fourchette -60% a +80%, soit
        # un ratio cible/cours entre 0.40 et 1.80). En dehors, on tente une
        # lecture en PER (petit nombre 3..60 nettement inferieur au cours), sinon
        # on ignore la valeur plutot que d afficher un potentiel absurde.
        nota_brut = cours_cibles.get(nom) or cours_cibles.get(d["nom_bvc"])
        cours_cible = None
        per = None
        signal_ana = "N/A"
        potentiel = None

        if nota_brut is not None and cours:
            try:
                nota = float(str(nota_brut).replace(" ","").replace(",","."))
                if nota > 0:
                    ratio = nota / cours
                    if 0.40 <= ratio <= 1.80:
                        # Cours cible plausible en MAD
                        cours_cible = round(nota, 2)
                    elif 3 <= nota <= 60 and ratio < 0.40:
                        # Lecture en PER (nettement sous le cours)
                        per = round(nota, 1)
                    # sinon : valeur aberrante -> ignoree (cible/PER restent None)
            except:
                pass

        # Potentiel hausse/baisse (borne de securite a +/-100%)
        if cours_cible and cours:
            potentiel = round((cours_cible - cours) / cours * 100, 2)
            if abs(potentiel) > 100:
                # garde-fou : potentiel hors-norme -> on invalide la cible
                cours_cible = None
                potentiel = None

        # Potentiel hausse/baisse
        if cours_cible and cours:
            potentiel = round((cours_cible - cours) / cours * 100, 2)

        # Signal analyste base sur potentiel
        if potentiel is not None:
            if potentiel > 15:    signal_ana = "ACHAT FORT"
            elif potentiel > 5:   signal_ana = "ACHAT"
            elif potentiel < -15: signal_ana = "VENTE"
            elif potentiel < -5:  signal_ana = "ALLEGEMENT"
            else:                 signal_ana = "CONSERVER"
        elif per is not None:
            # Pas de cours cible, signal base sur PER
            if per < 15:   signal_ana = "ACHAT"
            elif per < 25: signal_ana = "CONSERVER"
            else:          signal_ana = "PRUDENCE"

        # Depuis l historique : perf annuelle, beta, liquidite, 52 semaines
        hist = historique_csv.get(nom, [])
        perf_1an = None
        if len(hist) >= 250:
            c_actuel = hist[-1]["close"]
            c_1an    = hist[-250]["close"]
            perf_1an = round((c_actuel - c_1an) / c_1an * 100, 2) if c_1an else None

        beta      = beta_action(hist, proxy)
        liquidite = liquidite_moyenne(hist, 60)
        haut_52s, bas_52s = haut_bas_52s(hist)

        # Poids dans la capitalisation totale du marche
        poids_marche = None
        if cap and cap_total:
            poids_marche = round(cap / cap_total * 100, 2)

        resultats[nom] = {
            **d,
            "nb_titres"    : nb_titres,
            "poids_marche" : poids_marche,
            "beta"         : beta,
            "liquidite"    : liquidite,
            "haut_52s"     : haut_52s,
            "bas_52s"      : bas_52s,
            "cours_cible"  : cours_cible,
            "per"          : per,
            "potentiel"    : potentiel,
            "signal_ana"   : signal_ana,
            "perf_1an"     : perf_1an,
            "cap_fmt"      : fmt_mad(cap),
            "mise_a_jour"  : datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

    return resultats

# =============================================================================
# LECTURE HISTORIQUE CSV (pour perf 1 an)
# =============================================================================
def lire_historique():
    from collections import defaultdict
    pa = defaultdict(list)
    if not CSV_PATH.exists(): return pa
    with open(str(CSV_PATH), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nom = row["Action"].strip()
            if nom in ("MASI","MSI20"): continue
            ds = row["Date"].strip()
            if not ds: continue
            try:
                var = to_float(row.get("Variation","")) or 0.0
                try:    vol = int(float(row.get("Volume","0") or 0))
                except: vol = 0
                pa[nom].append({"date":ds, "close":float(row["Value"]),
                                "variation":var, "volume":vol})
            except: pass
    for n in pa: pa[n].sort(key=lambda x: x["date"])
    return pa

# =============================================================================
# INDICE DE MARCHE EQUIPONDERE (coherent avec 3_generer_html.py)
# Le MASI n etant pas renseigne dans le CSV, on reconstruit la variation
# moyenne de toutes les actions chaque jour pour servir de proxy au beta.
# =============================================================================
def construire_proxy_marche(historique):
    from collections import defaultdict
    par_date = defaultdict(list)
    for nom, ss in historique.items():
        for s in ss:
            par_date[s["date"]].append(s["variation"])
    return {d:(sum(v)/len(v)) for d,v in par_date.items() if v}

def calc_beta(asset_ret, market_ret):
    pairs = [(a,m) for a,m in zip(asset_ret,market_ret)
             if a is not None and m is not None]
    if len(pairs) < 30: return None
    n = len(pairs)
    ma = sum(a for a,_ in pairs)/n; mm = sum(m for _,m in pairs)/n
    cov = sum((a-ma)*(m-mm) for a,m in pairs)/n
    var = sum((m-mm)**2 for _,m in pairs)/n
    return round(cov/var,2) if var>0 else None

def beta_action(hist, proxy):
    """Beta close-to-close aligne par date avec le proxy de marche."""
    if len(hist) < 31: return None
    a_par_date = {}
    for i in range(1,len(hist)):
        c0 = hist[i-1]["close"]
        if c0:
            a_par_date[hist[i]["date"]] = (hist[i]["close"]-c0)/c0*100
    a_ret=[]; m_ret=[]
    for dte,r in a_par_date.items():
        if dte in proxy:
            a_ret.append(r); m_ret.append(proxy[dte])
    return calc_beta(a_ret, m_ret)

def liquidite_moyenne(hist, n=60):
    """Valeur moyenne echangee par seance (cours x volume) en MAD."""
    if not hist: return None
    derniers = hist[-n:] if len(hist) >= n else hist
    vals = [s["close"]*s["volume"] for s in derniers if s["volume"]]
    if not vals: return None
    return round(sum(vals)/len(vals), 0)

def haut_bas_52s(hist):
    """Plus haut / plus bas sur ~252 dernieres seances (52 semaines)."""
    if not hist: return (None, None)
    fenetre = hist[-252:] if len(hist) >= 252 else hist
    closes = [s["close"] for s in fenetre]
    return (round(max(closes),2), round(min(closes),2))

# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + SEP)
    print("  SCRIPT 4 - Recuperation des fondamentaux")
    print(SEP)
    print("  Heure : " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    print("")

    # 1. Scraping marche
    donnees_marche = scraper_marche()
    if not donnees_marche:
        print("  ERREUR : aucune donnee recuperee."); return

    # 2. Cours cibles
    cours_cibles = recuperer_cours_cibles()

    # 3. Historique
    print("  Lecture historique CSV ...")
    historique = lire_historique()
    print("  [OK] " + str(len(historique)) + " actions dans le CSV.")

    # 4. Calcul indicateurs
    print("  Calcul des indicateurs ...")
    resultats = calculer_indicateurs(donnees_marche, cours_cibles, historique)

    # 5. Sauvegarde JSON
    DOSSIER.mkdir(parents=True, exist_ok=True)
    with open(str(JSON_PATH), "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

    print("")
    print(SEP)
    print("  BILAN")
    print(SEP)
    print("  Actions analysees : " + str(len(resultats)))
    print("  Fichier JSON      : " + str(JSON_PATH))
    print("")

    # Afficher apercu
    print("  APERCU (10 premieres actions) :")
    print("  {:<22} {:>9} {:>8} {:>6} {:>14} {:>10} {:>10}".format(
          "Action","Cours","Poids%","Beta","Liquidite/j","Potentiel","Signal"))
    print("  " + "-"*92)
    for i,(nom,r) in enumerate(list(resultats.items())[:10]):
        pot = ("{:+.1f}%".format(r["potentiel"])) if r["potentiel"] is not None else "N/A"
        pds = ("{:.2f}".format(r["poids_marche"])) if r["poids_marche"] is not None else "N/A"
        bta = ("{:.2f}".format(r["beta"])) if r["beta"] is not None else "N/A"
        liq = fmt_mad(r["liquidite"]) if r["liquidite"] else "N/A"
        print("  {:<22} {:>9.2f} {:>8} {:>6} {:>14} {:>10} {:>10}".format(
              nom[:22], r["cours"], pds, bta, liq, pot, r["signal_ana"]))
    print(SEP + "\n")
    print("  Pour integrer dans le dashboard :")
    print("  python C:\\python\\3_generer_html.py")
    print("")

if __name__ == "__main__":
    main()
