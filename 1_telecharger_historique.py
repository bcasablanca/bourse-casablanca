# -*- coding: utf-8 -*-
# =============================================================================
# SCRIPT 1 - Telecharger l'historique complet depuis une date de debut
#            (v2 - API officielle BVC, via bvc.py)
# =============================================================================
# Reconstruit BCASAD.CSV a partir de zero pour les 81 valeurs cotees.
# L'ancien fichier est d'abord sauvegarde dans .\sauvegardes
#
# NB : pour la mise a jour quotidienne, utilisez le script 2 (il rattrape
# automatiquement tout retard). Ce script-ci ne sert qu'a repartir de zero ou
# a changer la profondeur de l'historique.
#
# Prerequis   : pip install requests certifi
# Utilisation : python 1_telecharger_historique.py            (demande la date)
#               python 1_telecharger_historique.py 01/01/2023 (sans question)
# =============================================================================

import subprocess, sys
for p in ["requests", "certifi"]:
    try: __import__(p)
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", p, "-q"], capture_output=True)

from datetime import datetime, date
import bvc

SEP = "=" * 62

def demander_date():
    if len(sys.argv) > 1:
        saisies = [sys.argv[1]]
    else:
        saisies = None
    while True:
        s = saisies.pop(0) if saisies else input("  Date de debut (JJ/MM/AAAA) [01/01/2024] : ").strip() or "01/01/2024"
        try:
            d = datetime.strptime(s, "%d/%m/%Y").date()
            if d > date.today():
                print("  Date future refusee."); continue
            return d
        except ValueError:
            print("  Format invalide. Ex : 01/01/2024")
            if len(sys.argv) > 1: sys.exit(1)

def main():
    print("\n" + SEP)
    print("  SCRIPT 1 - Telechargement historique Bourse de Casablanca")
    print(SEP + "\n")
    d = demander_date()
    print("\n  Periode : " + d.strftime("%d/%m/%Y") + " -> aujourd'hui")
    print("  Fichier : " + str(bvc.CSV_PATH) + "\n")
    try:
        b = bvc.mettre_a_jour(debut_force=d.strftime("%Y-%m-%d"), nouveau_fichier=True)
    except Exception as e:
        bvc.log("ECHEC du telechargement : " + str(e), "ERROR")
        sys.exit(1)
    print("\n" + SEP)
    print("  BILAN")
    print(SEP)
    print("  Lignes ecrites  : " + str(b["lignes_ajoutees"]))
    print("  Valeurs         : " + str(b["valeurs_mises_a_jour"]))
    print("  Derniere seance : " + str(b["derniere_seance"]))
    if b["erreurs"]:
        print("  En erreur       : " + ", ".join(b["erreurs"]))
    if b["sauvegarde"]:
        print("  Ancien fichier  : " + b["sauvegarde"])
    print(SEP)
    print("\n  Etapes suivantes : python 4_recuperer_fondamentaux.py")
    print("                     python 3_generer_html.py\n")

if __name__ == "__main__":
    main()
