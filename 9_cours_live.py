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
#   L'application Portefeuille peut aussi lancer ce script a la demande
#   (bouton Actualiser de l'onglet Seance) via l'API GitHub.
#
# Prerequis   : pip install requests certifi
# Utilisation : python 9_cours_live.py
# =============================================================================

import json, os, sys
from datetime import datetime, timezone
import bvc

SORTIE = bvc.DOSSIER / "cours_live.json"


def main():
    marche = bvc.marche_du_jour()
    actions = {}
    for a in marche["actions"]:
        if not a.get("cours"):
            continue
        r2 = lambda v: None if v is None else round(v, 2)
        actions[a["symbole"]] = {
            "nom": a["nom"],
            "cours": round(a["cours"], 2),
            "var": r2(a.get("variation_jour")),
            "ref": r2(a.get("cours_ref")),
            "haut": r2(a.get("haut_jour")),
            "bas": r2(a.get("bas_jour")),
            "cap": r2(a.get("volume_jour")),          # capitaux echanges (MAD)
            "qte": int(a.get("quantite_jour") or 0),  # titres echanges
            "nbt": int(a.get("nb_transactions") or 0),
        }
    if len(actions) < 20:
        print("ERREUR : seulement " + str(len(actions)) + " cours lus (page BVC modifiee ?)")
        sys.exit(1)

    masi = None
    try:
        masi = bvc.indices_du_jour()["valeurs"].get("MASI")
    except Exception as e:
        print("MASI indisponible : " + str(e)[:100])

    maintenant = datetime.now(timezone.utc)
    data = {
        "date": marche["seance"]["date"],
        "statut": marche["seance"]["statut"],
        "heure": datetime.now(bvc.TZ_MAROC).strftime("%H:%M"),
        "maj_iso": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "masi": masi,
        "actions": actions,
    }

    # Seance cloturee et cours inchanges : ne rien reecrire (evite des commits
    # inutiles). Pendant la seance on reecrit toujours : l'heure du releve
    # (maj_iso) sert au Portefeuille a savoir qu'un releve demande est arrive.
    if SORTIE.exists() and data["statut"] != "open":
        try:
            ancien = json.loads(SORTIE.read_text(encoding="utf-8"))
            if (ancien.get("actions") == actions and ancien.get("statut") == data["statut"]
                    and ancien.get("date") == data["date"]):
                print("Cours inchanges (" + str(len(actions)) + " valeurs, seance " + str(data["statut"]) + ")")
                return
        except Exception:
            pass

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
