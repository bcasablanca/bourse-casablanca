# -*- coding: utf-8 -*-
# =============================================================================
# SCRIPT 9 - Cours de la seance en cours (differes ~15 min par la BVC)
# =============================================================================
# Lit la page « Live Market » de casablanca-bourse.com (via bvc.py) et ecrit
# un petit fichier cours_live.json lu par l'application Portefeuille.
# Lance toutes les 15 minutes pendant la seance par GitHub Actions
# (.github/workflows/cours_live.yml). Ne touche pas a BCASAD.CSV.
#
# Format :
#   {"date": "2026-11-11", "statut": "open", "heure": "11:45",
#    "maj_iso": "2026-11-11T10:45:12Z", "masi": 17317.91,
#    "actions": {"ADH": {"nom": "Addoha", "cours": 40.1, "var": 0.28, "ref": 39.99,
#                        "haut": 40.5, "bas": 39.6, "cap": 51278472.36,
#                        "qte": 1280000, "nbt": 412}, ...}}
#   cap = capitaux echanges en MAD, qte = titres echanges, nbt = transactions.
#   Fiche « Cotation » du Portefeuille (ajout du 16/11/2026) :
#     ouv = premier cours, ach / vte = meilleure offre [prix, quantite]
#     (la BVC ne publie que la 1re ligne du carnet d'ordres),
#     r = releves de la seance [[heure, cours, titres echanges cumules], ...]
#     (une ligne a chaque releve ou le cours ou le volume a change),
#     veille = {"date", "actions": {SYM: {cours, var, ouv, haut, bas, qte, cap, nbt}}}
#     = derniere photo de la seance precedente.
#   L'application Portefeuille peut aussi lancer ce script a la demande
#   (bouton Actualiser de l'onglet Seance) via l'API GitHub.
#
# Prerequis   : pip install requests certifi
# Utilisation : python 9_cours_live.py
# =============================================================================

import json, os, sys, time
from datetime import datetime, timezone, timedelta
import bvc

SORTIE = bvc.DOSSIER / "cours_live.json"
CHAMPS_VEILLE = ("cours", "var", "ouv", "haut", "bas", "qte", "cap", "nbt")


def r2(v):
    return None if v is None else round(v, 2)


def offre(o):
    """{'prix': 38.46, 'quantite': 15} -> [38.46, 15] (None si vide)"""
    if not isinstance(o, dict):
        return None
    p, q = bvc._num(o.get("prix")), bvc._num(o.get("quantite"))
    return [round(p, 2), int(q or 0)] if p else None


def lire_ancien():
    try:
        return json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else None
    except Exception:
        return None


def photo_veille(actions):
    return {s: {k: a.get(k) for k in CHAMPS_VEILLE} for s, a in actions.items()}


def veille_depuis_historique(symboles, date_jour, limite_s=100):
    """Secours (1er lancement ou releve de la veille manquant) : derniere
    seance avant date_jour, lue dans l'historique BVC valeur par valeur."""
    debut = (datetime.strptime(date_jour, "%Y-%m-%d") - timedelta(days=12)).strftime("%Y-%m-%d")
    fin = (datetime.strptime(date_jour, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    res, date_v, t0 = {}, None, time.time()
    for s in symboles:
        if time.time() - t0 > limite_s:
            print("Historique de la veille : arret apres " + str(limite_s) + " s")
            break
        try:
            h = bvc._historique_api(s, debut, fin, False)
        except Exception as e:
            print("Veille " + s + " indisponible : " + str(e)[:80])
            continue
        if not h:
            continue
        d, p = h[-1], (h[-2] if len(h) > 1 else None)
        var = round((d["close"] / p["close"] - 1) * 100, 2) if p and p["close"] else None
        res[s] = {"cours": r2(d["close"]), "var": var, "ouv": r2(d["open"]), "haut": r2(d["high"]),
                  "bas": r2(d["low"]), "qte": int(d["volume"] or 0), "cap": r2(d["volume_mad"]),
                  "nbt": int(d["nb_transactions"] or 0)}
        date_v = max(date_v or d["date"], d["date"])
    return {"date": date_v, "actions": res} if res else None


def main():
    marche = bvc.marche_du_jour()
    actions = {}
    for a in marche["actions"]:
        if not a.get("cours"):
            continue
        actions[a["symbole"]] = {
            "nom": a["nom"],
            "cours": round(a["cours"], 2),
            "var": r2(a.get("variation_jour")),
            "ref": r2(a.get("cours_ref")),
            "ouv": r2(a.get("ouverture")),
            "haut": r2(a.get("haut_jour")),
            "bas": r2(a.get("bas_jour")),
            "cap": r2(a.get("volume_jour")),          # capitaux echanges (MAD)
            "qte": int(a.get("quantite_jour") or 0),  # titres echanges
            "nbt": int(a.get("nb_transactions") or 0),
            "ach": offre(a.get("achat")),
            "vte": offre(a.get("vente")),
        }
    if len(actions) < 20:
        print("ERREUR : seulement " + str(len(actions)) + " cours lus (page BVC modifiee ?)")
        sys.exit(1)

    date_seance = marche["seance"]["date"]
    heure = datetime.now(bvc.TZ_MAROC).strftime("%H:%M")
    ancien = lire_ancien() or {}
    meme_jour = ancien.get("date") == date_seance

    # Seance precedente : photo du dernier releve de l'ancienne seance,
    # sinon celle deja conservee, sinon l'historique BVC.
    veille = None
    if not meme_jour and ancien.get("actions") and ancien.get("date"):
        veille = {"date": ancien["date"], "actions": photo_veille(ancien["actions"])}
    elif meme_jour and isinstance(ancien.get("veille"), dict) and ancien["veille"].get("actions"):
        veille = ancien["veille"]
    if veille is None and date_seance:
        veille = veille_depuis_historique(sorted(actions), date_seance)

    # Releves de la seance (nouvelle ligne seulement si cours ou volume changent)
    anciennes = (ancien.get("actions") or {}) if meme_jour else {}
    for s, a in actions.items():
        r = list((anciennes.get(s) or {}).get("r") or [])
        if a["qte"] > 0 and (not r or r[-1][1] != a["cours"] or r[-1][2] != a["qte"]):
            r.append([heure, a["cours"], a["qte"]])
        if r:
            a["r"] = r[-40:]

    masi = None
    try:
        masi = bvc.indices_du_jour()["valeurs"].get("MASI")
    except Exception as e:
        print("MASI indisponible : " + str(e)[:100])

    maintenant = datetime.now(timezone.utc)
    data = {
        "date": date_seance,
        "statut": marche["seance"]["statut"],
        "heure": heure,
        "maj_iso": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "masi": masi,
        "actions": actions,
        "veille": veille,
    }

    # Seance cloturee et cours inchanges : ne rien reecrire (evite des commits
    # inutiles). Pendant la seance on reecrit toujours : l'heure du releve
    # (maj_iso) sert au Portefeuille a savoir qu'un releve demande est arrive.
    if (ancien and data["statut"] != "open" and ancien.get("actions") == actions
            and ancien.get("statut") == data["statut"] and meme_jour
            and ancien.get("veille") == veille):
        print("Cours inchanges (" + str(len(actions)) + " valeurs, seance " + str(data["statut"]) + ")")
        return

    tmp = SORTIE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(str(tmp), str(SORTIE))
    print("cours_live.json : " + str(len(actions)) + " valeurs, seance " + str(data["statut"])
          + " du " + str(data["date"]) + " a " + data["heure"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERREUR : " + str(e))
        sys.exit(1)
