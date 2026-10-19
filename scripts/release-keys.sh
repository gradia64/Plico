# Ruoli della chiave di rilascio di Plico, letti da scripts/verify-tag.sh.
# Unico punto in cui le impronte sono scritte (e nel README, per chi verifica).
# Modello ripreso da OllaDesk, più semplice: la CI di Plico non firma niente
# (gli allegati hanno SHA256SUMS e l'attestazione di provenienza di GitHub),
# quindi non c'è una sottochiave per la CI.
#
# La primaria [C], solo sulla macchina del maintainer: certifica le
# sottochiavi, è l'impronta di validpgpkeys nel PKGBUILD. Non firma nulla.
RELEASE_PRIMARY="${PLICO_RELEASE_PRIMARY:-184307C7A1585AFAD7F09DF6EBC8B4A0FFD5B91F}"
# Sottochiavi che possono firmare i TAG: solo quelle del maintainer, mai nella
# CI. Più di una, separate da spazi, solo durante una rotazione.
TAG_SIGNING_SUBKEYS="${PLICO_TAG_SIGNING_SUBKEYS:-E0C771BBB276A114D0B8C591C5DDC0745643FA72}"
