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
#    "actions": {"ADH": {"nom": "Addoha", "cours": 40.1, "var": 0.28}, ...}}
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
        actions[a["symbole"]] = {
            "nom": a["nom"],
            "cours": round(a["cours"], 2),
            "var": None if a.get("variation_jour") is None else round(a["variation_jour"], 2),
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

    # Ne reecrire que si les cours ont change (evite des commits inutiles)
    if SORTIE.exists():
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
