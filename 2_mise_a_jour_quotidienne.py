# -*- coding: utf-8 -*-
# =============================================================================
# SCRIPT 2 - Mise a jour quotidienne de BCASAD.CSV  (v2 - API officielle BVC)
# =============================================================================
# Source : API officielle de casablanca-bourse.com (via bvc.py).
# casased n'est plus utilise : il ne renvoie plus de donnees depuis juin 2026.
#
# Fonctionnement :
#   - pour CHAQUE valeur cotee, re-telecharge tout son historique officiel
#     (~45 s pour 81 valeurs) : rattrape automatiquement les retards, meme de
#     plusieurs mois, ajoute les valeurs nouvellement cotees et garde des cours
#     ajustes coherents apres chaque dividende / division de nominal
#     (reglage COURS_AJUSTES dans bvc.py) ;
#   - n'enregistre jamais la seance du jour tant qu'elle n'est pas cloturee ;
#   - enregistre la cloture du MASI et du MSI20 quand la seance est terminee ;
#   - sauvegarde le CSV dans .\sauvegardes avant toute modification, puis
#     ecrit le nouveau fichier de facon atomique ;
#   - code retour 1 + message clair en cas d'echec (plus de panne silencieuse).
#
# Prerequis   : pip install requests certifi
# Utilisation : python 2_mise_a_jour_quotidienne.py
# Planification Windows (tous les jours ouvres a 16h30, apres la cloture) :
#   schtasks /create /tn "BourseCasa" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:30 /f
#            /tr "cmd /c cd /d . && python 2_mise_a_jour_quotidienne.py && python 4_recuperer_fondamentaux.py && python 3_generer_html.py"
# =============================================================================

import subprocess, sys
for p in ["requests", "certifi"]:
    try: __import__(p)
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", p, "-q"], capture_output=True)

from datetime import datetime
import bvc

SEP = "=" * 62

def main():
    print("\n" + SEP)
    print("  SCRIPT 2 - Mise a jour quotidienne (API officielle BVC)")
    print(SEP)
    print("  Heure   : " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    print("  Fichier : " + str(bvc.CSV_PATH))
    print("  Cours   : " + ("ajustes (dividendes / divisions)" if bvc.COURS_AJUSTES else "bruts"))
    print("")

    try:
        b = bvc.mettre_a_jour()
    except Exception as e:
        bvc.log("ECHEC de la mise a jour : " + str(e), "ERROR")
        print("\n  Le CSV n'a pas ete modifie. Verifiez la connexion Internet")
        print("  puis relancez le script. Detail dans mise_a_jour.log\n")
        sys.exit(1)

    print("")
    print(SEP)
    print("  RAPPORT")
    print(SEP)
    print("  Derniere seance avant  : " + str(b["derniere_avant"]))
    print("  Derniere seance apres  : " + str(b["derniere_seance"]))
    print("  Lignes ajoutees        : " + str(b["lignes_ajoutees"]))
    print("  Cours ajustes/corriges : " + str(b["cours_ajustes"]))
    print("  Valeurs mises a jour   : " + str(b["valeurs_mises_a_jour"]))
    if b["nouvelles_valeurs"]:
        print("  Nouvelles valeurs      : " + ", ".join(b["nouvelles_valeurs"]))
    if b["erreurs"]:
        print("  Valeurs en erreur      : " + ", ".join(b["erreurs"]))
    if b["sauvegarde"]:
        print("  Sauvegarde             : " + b["sauvegarde"])
    print("  Duree                  : " + str(b["duree_s"]) + " s")
    print(SEP + "\n")

    bvc.log("Mise a jour OK : +" + str(b["lignes_ajoutees"]) + " lignes, derniere seance "
            + str(b["derniere_seance"]) + (", erreurs: " + ",".join(b["erreurs"]) if b["erreurs"] else ""))

    if not bvc.verifier_fraicheur(b["derniere_seance"], seuil_jours_ouvres=4):
        bvc.log("ALERTE : la derniere seance du CSV (" + str(b["derniere_seance"]) +
                ") date de plus de 4 jours ouvres. Donnees BVC indisponibles ?", "ERROR")
        sys.exit(2)

if __name__ == "__main__":
    main()
