# -*- coding: utf-8 -*-
# =============================================================================
# bvc.py - Acces aux donnees OFFICIELLES de la Bourse de Casablanca
# =============================================================================
# Module partage par les scripts 1, 2 et 4. Remplace casased (qui ne renvoie
# plus rien depuis juin 2026) et le scraping du tableau HTML (supprime lors de
# la refonte du site casablanca-bourse.com).
#
# Sources utilisees (celles qu'utilise le site BVC lui-meme) :
#   - /api/boursenova/stock-historical : historique quotidien par valeur
#     (ouverture, plus haut, plus bas, dernier cours, titres echanges, ...)
#   - /live-market/actions : cotations du jour des 81 valeurs (JSON embarque)
#   - /live-market/indices : valeurs du jour du MASI, MSI20, ...
#
# Dependances : requests, certifi (pas de pandas, pas de casased)
#
# Securite TLS : le serveur de la BVC n'envoie pas son certificat
# intermediaire. Au lieu de desactiver la verification (verify=False), on
# ajoute cet intermediaire (fichier bvc_intermediate.pem) au magasin certifi.
# =============================================================================

import csv, json, os, re, shutil, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

DOSSIER   = Path(os.environ.get("BOURSE_DOSSIER") or Path(__file__).resolve().parent)
CSV_PATH  = DOSSIER / "BCASAD.CSV"
LOG_PATH  = DOSSIER / "mise_a_jour.log"
SAUV_DIR  = DOSSIER / "sauvegardes"
CSV_COLS  = ["Date", "Value", "Min", "Max", "Variation", "Volume", "Action", "index"]
INDICES   = ("MASI", "MSI20")
HIST_START_DEFAUT = "2024-01-02"
NB_SAUVEGARDES = 10
# Cours ajustes des divisions de nominal et des dividendes (comme "Adj Close").
# Indispensable pour l'analyse technique : ex. Managem a divise son nominal par
# 10 le 27/07/2026 -> en cours bruts, faux krach de -89 % sur les graphiques.
# Le dernier cours reste identique au cours reel. False = cours bruts.
COURS_AJUSTES = True
# Une valeur jamais vue dans le CSV n'est ajoutee qu'avec au moins N seances
# (evite les valeurs suspendues comme SAMIR qui n'ont qu'un cours de reference).
MIN_SEANCES_NOUVELLE_VALEUR = 5

BASE = "https://www.casablanca-bourse.com"
API_HIST = BASE + "/api/boursenova/stock-historical"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# Heure legale du Maroc (GMT+1 ou GMT+0 selon la periode : Ramadan, changements
# officiels...). La base officielle des fuseaux suit ces changements ; a defaut
# (module tzdata absent sous Windows), repli sur GMT+1.
try:
    from zoneinfo import ZoneInfo
    TZ_MAROC = ZoneInfo("Africa/Casablanca")
except Exception:
    TZ_MAROC = timezone(timedelta(hours=1))

# -----------------------------------------------------------------------------
# Correspondance symbole BVC -> nom utilise dans BCASAD.CSV / fondamentaux.json
# Les noms historiques (issus de casased) sont conserves pour ne pas casser
# l'historique existant. Une nouvelle valeur absente d'ici sera ajoutee
# automatiquement sous son libelle BVC.
# -----------------------------------------------------------------------------
SYMBOLE_VERS_NOM = {
    "ADH": "Addoha",            "ADI": "Alliances",         "AFI": "Afric Indus",
    "AFM": "AFMA",              "AGM": "Agma",              "AKT": "Akdital",
    "ALM": "Aluminium Maroc",   "ARD": "Aradei Capital",    "ATH": "Auto Hall",
    "ATL": "ATLANTASANAD",      "ATW": "Attijariwafa",      "BAL": "BALIMA",
    "BCI": "BMCI",              "BCP": "BCP",               "BOA": "BOA",
    "CAP": "Cash Plus",         "CDM": "CDM",               "CFG": "CFG Bank",
    "CIH": "CIH",               "CMA": "Ciments Maroc",     "CMG": "CMGP Group",
    "CMT": "CMT",               "COL": "Colorado",          "CRS": "Cartier Saada",
    "CSR": "COSUMAR",           "CTM": "CTM",               "DHO": "Delta Holding",
    "DIS": "DIAC Salaf",        "DLM": "Delattre Levivier", "DRI": "Dari Couspate",
    "DWY": "DISWAY",            "DYT": "Disty Technolog",   "EQD": "EQDOM",
    "FBR": "FENIE BROSSETTE",   "GAZ": "Afriquia Gaz",      "GTM": "SGTM",
    "HPS": "HPS",               "IAM": "IAM",               "IBC": "IBMaroc",
    "IMO": "Immr Invest",       "INV": "INVOLYS",           "JET": "Jet Contractors",
    "LBV": "LABEL VIE",         "LES": "Lesieur Cristal",   "LHM": "LafargeHolcim",
    "M2M": "M2M Group",         "MAB": "Maghrebail",        "MDP": "Med Paper",
    "MIC": "Microdata",         "MLE": "Maroc Leasing",     "MNG": "Managem",
    "MOX": "Maghreb Oxygene",   "MSA": "SODEP",             "MUT": "Mutandis",
    "NEJ": "Auto Nejma",        "NKL": "Ennakl",            "OUL": "Oulmes",
    "PRO": "PROMOPHARM",        "RDS": "Res.Dar Saada",     "REB": "Rebab Company",
    "RIS": "Risma",             "S2M": "S2M",               "SAH": "Sanlam Maroc",
    "SAM": "Samir",             "SBM": "Ste Boissons",      "SID": "Sonasid",
    "SLF": "SALAFIN",           "SMI": "SMI",               "SNA": "Stokvis Nord Afr",
    "SNP": "SNEP",              "SOT": "SOTHEMA",           "SRM": "SRM",
    "STR": "STROC Indus",       "T2S": "T2S GROUP HOLDING", "TGC": "TGCC",
    "TMA": "Total Maroc",       "TQM": "TAQA Morocco",      "UMR": "Unimer",
    "VCN": "Vicenne",           "WAA": "Wafa Assur",        "ZDJ": "Zellidja",
}


# =============================================================================
# JOURNAL
# =============================================================================
def log(msg, niveau="INFO"):
    ligne = "{}  {:<8}  {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), niveau, msg)
    print(ligne)
    sys.stdout.flush()
    try:
        with open(str(LOG_PATH), "a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except Exception:
        pass


# =============================================================================
# HTTP
# =============================================================================
def _ca_bundle():
    """certifi + certificat intermediaire BVC -> fichier PEM (verification TLS active)."""
    import certifi
    inter = Path(__file__).resolve().parent / "bvc_intermediate.pem"
    if not inter.exists():
        return True  # verification standard
    cible = Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp") / "bvc_ca_bundle.pem"
    try:
        contenu = Path(certifi.where()).read_text(encoding="utf-8") + "\n" + inter.read_text(encoding="utf-8")
        if not cible.exists() or cible.read_text(encoding="utf-8") != contenu:
            cible.write_text(contenu, encoding="utf-8")
        return str(cible)
    except Exception:
        return True

_SESSION = None
def session():
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
        s.verify = _ca_bundle()
        _SESSION = s
    return _SESSION

def _get(url, params=None, essais=4, timeout=40, accept="application/json"):
    """GET avec nouvelles tentatives (attente progressive) sur erreur reseau / 5xx / 429."""
    derniere = None
    for i in range(essais):
        try:
            r = session().get(url, params=params, timeout=timeout, headers={"Accept": accept})
            if r.status_code == 200:
                return r
            derniere = "HTTP " + str(r.status_code)
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.RequestException as e:
            derniere = type(e).__name__ + ": " + str(e)[:120]
        time.sleep(2 * (i + 1))
    raise RuntimeError("Echec " + url + " : " + str(derniere))

def _drupal_settings(chemin):
    r = _get(BASE + chemin, accept="text/html")
    m = re.search(r'data-drupal-selector="drupal-settings-json">(.*?)</script>', r.text, re.S)
    if not m:
        raise RuntimeError("Donnees introuvables dans la page " + chemin + " (structure du site modifiee ?)")
    return json.loads(m.group(1))


# =============================================================================
# DONNEES BVC
# =============================================================================
def _num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None

def _seance_iso(s):
    """'04/11/2026' -> '2026-11-04'"""
    return datetime.strptime(s.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")

def historique(symbole, debut_iso, fin_iso, ajuste=None):
    """Historique quotidien d'une valeur.
    ajuste : cours ajustes (defaut = COURS_AJUSTES).
    Retourne une liste triee de dicts : date, open, high, low, close, volume (titres),
    volume_mad, nb_transactions, capitalisation.

    En mode ajuste, la serie BRUTE (complete) sert de base et on lui applique le
    coefficient ajuste/brut fourni par la BVC : la serie ajustee de l'API a en
    effet des trous (ex. seances du 14 au 22/07/2026 absentes). Pour une seance
    sans coefficient, on reprend celui de la seance suivante (a defaut, la
    precedente)."""
    if ajuste is None:
        ajuste = COURS_AJUSTES
    brut = _historique_api(symbole, debut_iso, fin_iso, False)
    if not ajuste or not brut:
        return brut
    adj = {x["date"]: x["close"] for x in _historique_api(symbole, debut_iso, fin_iso, True)}
    coefs = [adj[b["date"]] / b["close"] if b["date"] in adj and b["close"] else None for b in brut]
    suivant = None
    for i in range(len(coefs) - 1, -1, -1):
        if coefs[i] is None: coefs[i] = suivant
        else: suivant = coefs[i]
    precedent = None
    for i in range(len(coefs)):
        if coefs[i] is None: coefs[i] = precedent
        else: precedent = coefs[i]
    for b, k in zip(brut, coefs):
        if k and abs(k - 1) > 1e-9:
            for c in ("open", "high", "low", "close"):
                if b[c] is not None:
                    b[c] = b[c] * k
    return brut

def _historique_api(symbole, debut_iso, fin_iso, ajuste):
    res, page = [], 1
    while True:
        params = {
            "instrument": symbole.strip(), "market": "comptant", "type": "actions",
            "startDate": debut_iso, "endDate": fin_iso,
            "pageNumber": page, "pageSize": 1000,
        }
        if ajuste:
            params["isCoursAjuste"] = "true"
        r = _get(API_HIST, params=params)
        j = r.json()
        items = j.get("items") or []
        for it in items:
            close = _num(it.get("dernierCours"))
            if not close or not it.get("seance"):
                continue
            res.append({
                "date": _seance_iso(it["seance"]),
                "open": _num(it.get("ouverture")),
                "high": _num(it.get("plusHaut")),
                "low": _num(it.get("plusBas")),
                "close": close,
                "volume": int(_num(it.get("titresEchanges")) or 0),
                "volume_mad": _num(it.get("volumeEchanges")),
                "nb_transactions": _num(it.get("nbTransactions")),
                "capitalisation": _num(it.get("capitalisation")),
            })
        total = int(j.get("totalCount") or 0)
        if not items or page * 1000 >= total:
            break
        page += 1
    dedup = {x["date"]: x for x in res}
    return [dedup[d] for d in sorted(dedup)]

def _etat_seance(cfg_live):
    s = (cfg_live or {}).get("session") or {}
    ts = s.get("timestamp")
    d = datetime.fromtimestamp(ts, TZ_MAROC).strftime("%Y-%m-%d") if ts else None
    return {"statut": s.get("status") or "?", "date": d}

def marche_du_jour():
    """Cotations du jour des actions (page Live Market).
    Retourne {'seance': {'statut','date'}, 'actions': [ {...} ]}"""
    lm = _drupal_settings("/live-market/actions").get("live_market") or {}
    secteurs = {}
    actions = []
    for a in lm.get("actions") or []:
        sym = (a.get("symbol") or "").strip()
        if not sym:
            continue
        lib = ((a.get("emetteur") or {}).get("fr") or sym).strip()
        actions.append({
            "symbole": sym,
            "nom": nom_csv(sym, lib),
            "emetteur": lib,
            "secteur": ((a.get("secteur") or {}).get("fr") or "").strip(),
            "statut": ((a.get("statut") or {}).get("fr") or "").strip(),
            "cours": _num(a.get("dernierCours")) or _num(a.get("reference")),
            "dernier": _num(a.get("dernierCours")),
            "cours_ref": _num(a.get("reference")),
            "ouverture": _num(a.get("ouverture")),
            "haut_jour": _num(a.get("plusHaut")),
            "bas_jour": _num(a.get("plusBas")),
            "variation_jour": _num(a.get("variation")),
            "quantite_jour": _num(a.get("quantite")),
            "volume_jour": _num(a.get("volume")),
            "nb_transactions": _num(a.get("nbTransactions")),
            "capitalisation": _num(a.get("capitalisation")),
            "nb_titres": _num(a.get("nombreTitres")),
        })
    return {"seance": _etat_seance(lm), "actions": actions}

def indices_du_jour():
    """Valeurs du jour des indices. Retourne {'seance': {...}, 'valeurs': {code: valeur}}"""
    lm = _drupal_settings("/live-market/indices").get("live_market") or {}
    vals = {}
    groupes = (lm.get("indices") or {})
    for grp in groupes.values():
        for ix in grp or []:
            code = (ix.get("code") or "").strip()
            v = _num(ix.get("value"))
            if code and v:
                vals[code] = v
    return {"seance": _etat_seance(lm), "valeurs": vals}

def nom_csv(symbole, libelle=None):
    sym = symbole.strip()
    return SYMBOLE_VERS_NOM.get(sym) or (libelle or sym).strip()


# =============================================================================
# CSV
# =============================================================================
def lire_csv():
    """Retourne (cours, indices) :
       cours   = {(date, action): row}
       indices = {(date, 'MASI'|'MSI20'): valeur}  (les lignes indice vides sont ignorees)"""
    cours, indices = {}, {}
    if not CSV_PATH.exists():
        return cours, indices
    with open(str(CSV_PATH), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            nom = (row.get("Action") or "").strip()
            if nom in INDICES:
                # format officiel : date dans 'index' ; quelques anciennes lignes
                # ont la date dans 'Date' -> on les recupere aussi
                d = (row.get("index") or "").strip() or (row.get("Date") or "").strip()
                v = (row.get("Value") or "").strip()
                if d and v:
                    try: indices[(d, nom)] = float(v)
                    except ValueError: pass
                continue
            d = (row.get("Date") or "").strip()
            if d and nom and (row.get("Value") or "").strip():
                cours[(d, nom)] = {k: (row.get(k) or "").strip() for k in CSV_COLS}
    return cours, indices

def sauvegarder_csv():
    if not CSV_PATH.exists():
        return None
    SAUV_DIR.mkdir(parents=True, exist_ok=True)
    cible = SAUV_DIR / ("BCASAD_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".CSV")
    shutil.copy2(str(CSV_PATH), str(cible))
    anciennes = sorted(SAUV_DIR.glob("BCASAD_*.CSV"))
    for p in anciennes[:-NB_SAUVEGARDES]:
        try: p.unlink()
        except Exception: pass
    return cible

def ecrire_csv(cours, indices):
    """Ecriture atomique (fichier temporaire puis remplacement)."""
    tmp = CSV_PATH.with_suffix(".tmp")
    with open(str(tmp), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for k in sorted(cours):
            w.writerow(cours[k])
        for (d, nom) in sorted(indices):
            w.writerow({"Date": "", "Value": "{:.2f}".format(indices[(d, nom)]), "Min": "", "Max": "",
                        "Variation": "", "Volume": "", "Action": nom, "index": d})
    os.replace(str(tmp), str(CSV_PATH))

def recalculer_variations(cours, actions):
    """Variation % = (cloture - cloture precedente) / cloture precedente,
    recalculee sur toute la serie des actions indiquees."""
    par_action = {}
    for (d, nom), row in cours.items():
        if nom in actions:
            par_action.setdefault(nom, []).append((d, row))
    for nom, serie in par_action.items():
        serie.sort(key=lambda x: x[0])
        prev = None
        for d, row in serie:
            close = float(row["Value"])
            if prev:
                row["Variation"] = "{:.2f}".format((close - prev) / prev * 100)
            elif not row.get("Variation"):
                row["Variation"] = "0.00"   # 1re seance : on garde la valeur connue
            prev = close


# =============================================================================
# MISE A JOUR (moteur commun aux scripts 1 et 2)
# =============================================================================
def jours_ouvres_entre(d1_iso, d2_iso):
    d = datetime.strptime(d1_iso, "%Y-%m-%d").date()
    fin = datetime.strptime(d2_iso, "%Y-%m-%d").date()
    n = 0
    while d <= fin:
        if d.weekday() < 5: n += 1
        d += timedelta(days=1)
    return n

def mettre_a_jour(debut_force=None, nouveau_fichier=False, pause=0.3):
    """Rafraichit BCASAD.CSV depuis l'API officielle.

    Pour chaque valeur cotee, TOUT l'historique (depuis la 1re date du CSV) est
    re-telecharge : les seances manquantes sont ajoutees et les cours deja
    presents sont remplaces par les cours officiels (ajustes si COURS_AJUSTES),
    ce qui garde une serie coherente apres chaque dividende ou division de
    nominal. Les lignes que l'API ne fournit pas (valeurs radiees, seances
    anterieures) sont conservees telles quelles.

    debut_force     : date ISO de debut imposee (script 1)
    nouveau_fichier : repart d'un CSV vide (script 1)
    Retourne un dict bilan ; leve RuntimeError si la source est inaccessible."""
    t0 = time.time()
    aujourd_hui = datetime.now(TZ_MAROC).strftime("%Y-%m-%d")

    cours, indices = ({}, {}) if nouveau_fichier else lire_csv()
    nb_lignes_avant = len(cours)
    dates_csv = sorted({d for d, _ in cours})
    hist_start = debut_force or (dates_csv[0] if dates_csv else HIST_START_DEFAUT)
    derniere_avant = dates_csv[-1] if dates_csv else None
    log("CSV : " + str(nb_lignes_avant) + " lignes, derniere seance = " + str(derniere_avant))

    # 1. Liste des valeurs cotees + etat de la seance
    try:
        marche = marche_du_jour()
        valeurs = [(a["symbole"], a["nom"]) for a in marche["actions"]]
        live = {a["symbole"]: a for a in marche["actions"]}
        seance = marche["seance"]
        log("Live Market : " + str(len(valeurs)) + " valeurs, seance " + seance["statut"] + " (" + str(seance["date"]) + ")")
    except Exception as e:
        log("Liste Live Market indisponible (" + str(e)[:100] + ") -> liste interne utilisee", "WARNING")
        valeurs = [(s, n) for s, n in SYMBOLE_VERS_NOM.items()]
        live = {}
        seance = {"statut": "?", "date": None}
    # Ne jamais enregistrer la seance du jour tant qu'elle n'est pas cloturee
    exclure = aujourd_hui if seance["statut"] != "closed" else None

    par_action = {}
    for (d, nom) in cours:
        par_action.setdefault(nom, set()).add(d)

    # 2. Telechargement de l'historique officiel, valeur par valeur
    ajouts = {}          # {nom: nb seances ajoutees}
    rafraichies = set()  # valeurs dont la serie vient de l'API
    nb_corrigees = 0
    erreurs = []
    for i, (sym, nom) in enumerate(valeurs, 1):
        prefixe = "  [{:>3}/{}] {:<6} {:<22}".format(i, len(valeurs), sym, nom[:22])
        try:
            hist = historique(sym, hist_start, aujourd_hui)
        except Exception as e:
            erreurs.append(sym)
            print(prefixe + " ERREUR " + str(e)[:70]); continue
        hist = [b for b in hist if b["date"] != exclure and b["date"] >= hist_start]
        # Seance cloturee mais pas encore publiee dans l'historique (la BVC
        # l'ajoute le lendemain) -> cours de cloture du Live Market. Le
        # lendemain, la ligne officielle de l'historique la remplace.
        d_s, a = seance["date"], live.get(sym)
        if (seance["statut"] == "closed" and d_s and a and a.get("dernier")
                and (not hist or hist[-1]["date"] < d_s)):
            hist.append({"date": d_s, "close": a["dernier"],
                         "high": a["haut_jour"], "low": a["bas_jour"],
                         "volume": int(a["quantite_jour"] or 0)})
        anciennes = par_action.get(nom, set())
        if not hist:
            print(prefixe + " aucune seance"); time.sleep(pause); continue
        if not anciennes and len(hist) < MIN_SEANCES_NOUVELLE_VALEUR:
            print(prefixe + " ignoree (" + str(len(hist)) + " seance(s) : valeur suspendue ?)")
            time.sleep(pause); continue

        # La serie API fait foi a partir de sa 1re seance : on retire les
        # anciennes lignes de cette valeur sur la meme periode.
        premiere = hist[0]["date"]
        anciennes_lignes = {d: cours.pop((d, nom)) for d in list(anciennes) if d >= premiere}
        n_new = n_mod = 0
        for b in hist:
            d = b["date"]
            ligne = {
                "Date": d, "Value": "{:.2f}".format(b["close"]),
                "Min": "{:.2f}".format(b["low"] if b["low"] else b["close"]),
                "Max": "{:.2f}".format(b["high"] if b["high"] else b["close"]),
                "Variation": "", "Volume": str(b["volume"]),
                "Action": nom, "index": "",
            }
            old = anciennes_lignes.get(d)
            if old is None:
                n_new += 1
            else:
                ligne["Variation"] = old.get("Variation", "")
                if (old["Value"], old["Min"], old["Max"]) != (ligne["Value"], ligne["Min"], ligne["Max"]):
                    n_mod += 1
            cours[(d, nom)] = ligne
        rafraichies.add(nom)
        nb_corrigees += n_mod
        if n_new:
            ajouts[nom] = n_new
        etat = []
        if n_new: etat.append("+" + str(n_new) + " seance(s)")
        if n_mod: etat.append(str(n_mod) + " cours ajuste(s)")
        print(prefixe + " " + (", ".join(etat) if etat else "a jour"))
        time.sleep(pause)

    if not valeurs or len(erreurs) > len(valeurs) / 2:
        raise RuntimeError(str(len(erreurs)) + "/" + str(len(valeurs)) +
                           " valeurs en erreur : API BVC inaccessible. CSV NON modifie.")

    recalculer_variations(cours, rafraichies)

    # 3. Indices du jour (MASI / MSI20) - uniquement seance cloturee
    ix_ajoutes = False
    try:
        ix = indices_du_jour()
        d_ix = ix["seance"]["date"]
        if ix["seance"]["statut"] == "closed" and d_ix and any(d == d_ix for d, _ in cours):
            for code in INDICES:
                if code in ix["valeurs"]:
                    if indices.get((d_ix, code)) != ix["valeurs"][code]:
                        ix_ajoutes = True
                    indices[(d_ix, code)] = ix["valeurs"][code]
            log("Indices du " + d_ix + " : " + ", ".join(
                c + "=" + "{:.2f}".format(ix["valeurs"][c]) for c in INDICES if c in ix["valeurs"]))
        else:
            log("Indices non enregistres (seance " + ix["seance"]["statut"] + ")")
    except Exception as e:
        log("Indices indisponibles : " + str(e)[:100], "WARNING")

    # 4. Ecriture (avec sauvegarde) seulement si quelque chose a change
    nb_ajouts = sum(ajouts.values())
    sauvegarde = None
    if nb_ajouts or nb_corrigees or nouveau_fichier or _a_nettoyer() or ix_ajoutes:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        sauvegarde = sauvegarder_csv()
        ecrire_csv(cours, indices)

    dates_apres = sorted({d for d, _ in cours})
    bilan = {
        "lignes_ajoutees": nb_ajouts,
        "cours_ajustes": nb_corrigees,
        "valeurs_mises_a_jour": len(ajouts),
        "nouvelles_valeurs": sorted(n for n in ajouts if n not in par_action),
        "erreurs": erreurs,
        "derniere_seance": dates_apres[-1] if dates_apres else None,
        "derniere_avant": derniere_avant,
        "sauvegarde": str(sauvegarde) if sauvegarde else None,
        "duree_s": round(time.time() - t0, 1),
    }
    return bilan

def _a_nettoyer():
    """Vrai si le CSV contient des lignes MASI/MSI20 vides (heritage de l'ancien script 2)."""
    if not CSV_PATH.exists():
        return False
    with open(str(CSV_PATH), encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("Action") or "").strip() in INDICES and not (row.get("Value") or "").strip():
                return True
    return False

def verifier_fraicheur(derniere_seance, seuil_jours_ouvres=3):
    """Alerte si la derniere seance du CSV est trop ancienne (evite les pannes silencieuses)."""
    if not derniere_seance:
        return False
    hier = (datetime.now(TZ_MAROC).date() - timedelta(days=1)).strftime("%Y-%m-%d")
    retard = jours_ouvres_entre(derniere_seance, hier) - 1
    return retard < seuil_jours_ouvres
