"""Avvio di Plico installato da pacchetto (AppImage, e poi .deb e Arch).

Installato in /usr/share/plico/launcher.py ed eseguito dall'avvio del
pacchetto (nell'AppImage dall'AppRun, con il Python incluso).

NON `python3 -m plico.app`: con -m Python mette la cartella corrente in
sys.path[0], davanti a tutto, e un json.py (o un checkout di plico/) nella
cartella di avvio verrebbe importato al posto dei moduli veri. Eseguendo uno
script, sys.path[0] è la cartella dello script: /usr/share/plico.
"""
import sys

from plico.app import main

sys.exit(main())
