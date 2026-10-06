# TMB Lost & Found — app Android

App de registre d'objectes perduts per a operaris de TMB (NFC del vehicle → 2 fotos → etiquetes → enviament a l'API, amb funcionament sense connexió).

Obrir **aquesta carpeta** (`client/android`) amb Android Studio i executar `app`.

```bash
./gradlew assembleDebug        # compilar
./gradlew testDebugUnitTest    # tests unitaris
```

Per defecte usa una API simulada (`lostfound.useMockApi=true` a `gradle.properties`).

Documentació completa: [`docs/app-mobil/`](../../docs/app-mobil/README.md)
