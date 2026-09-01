![MarkGuardiola](https://github.com/marklikesyou/Mark-Guardiola/releases/download/v1.0.0/markguardiola-cover.jpg)

# MarkGuardiola

ho costruito Markguardiola come mio assistente locale per il Fantacalcio. Importa la lega, raccoglie dati reali, allena i modelli (non c'é L'EI AI COL LARGE LENGUEGE MODELLL) e prepara indicazioni per formazione e mercato. Tutto gira sul tuo device.

La prima installazione ricostruisce lo storico, aggiorna la stagione corrente, genera le previsioni e crea la lega Tutorial. I giocatori, le partite e le previsioni del tutorial arrivano dalla pipeline dati reale.

## Cosa puoi fare

- Preparare la formazione della giornata in base a modulo, avversario e disponibilità
- Consultare la rosa su un campo che si adatta allo schema scelto
- Scorrere i giocatori per ruolo e aprire le relative schede
- Valutare svincoli, acquisti e alternative disponibili sul mercato
- Importare rosa, avversari e mercato da CSV
- Configurare budget, ruoli, moduli, punteggi e sostituzioni della lega
- Consultare probabilità di titolarità, minuti attesi, bonus, cartellini e rendimento previsto
- Confrontare le decisioni tramite simulazioni riproducibili

## Come funziona

Il backend acquisisce dati storici e correnti, risolve le identità di squadre e giocatori, costruisce feature point in time e allena un insieme di modelli per ogni target. Le previsioni alimentano il motore decisionale usato dalle pagine Giornata, Mercato e Giocatori.

I dati principali arrivano da football-data.co.uk, PannaData e Understat. API Football e football-data.org aggiungono informazioni correnti quando viene configurata una chiave. FBref è disponibile come fonte facoltativa tramite `soccerdata`.

## Cosa ti Serve

- Git
- Docker Desktop oppure Docker Engine con Docker Compose
- macOS o Linux su ARM64 o x86_64
- Windows su ARM64 o x86_64 con container Linux
- Spazio libero per immagini Docker, dati storici e modelli

La ricostruzione completa al primo avvio può richiedere alcune ore. La durata dipende dalla connessione, dalla macchina e dalla disponibilità delle fonti.

## Installazione su macOS e Linux

Clona la repo con un account GitHub autorizzato.

```bash
git clone https://github.com/marklikesyou/Mark-Guardiola.git
cd Mark-Guardiola
MARK_INSTALL_DIR="$PWD" bash scripts/install.sh
```

L'installer crea un file `.env` privato, genera una password per PostgreSQL, costruisce le immagini, applica le migrazioni, prepara dati e modelli, poi avvia l'app.

dopo apri [http://localhost:3000](http://localhost:3000).

## Installazione su Windows

Esegui PowerShell con Docker Desktop già avviato.

```powershell
git clone https://github.com/marklikesyou/Mark-Guardiola.git
Set-Location Mark-Guardiola
$env:MARK_INSTALL_DIR = (Get-Location).Path
.\scripts\install.ps1
```

Al termine apri [http://localhost:3000](http://localhost:3000).

## Fonti dati e API key

Le chiavi sono facoltative. Inseriscile nel file `.env` senza pubblicarlo.

| Variabile | Utilizzo |
| --- | --- |
| `MARK_API_FOOTBALL_KEY` | Formazioni, infortuni, trasferimenti, eventi correnti e foto dei giocatori della tua rosa |
| `MARK_FOOTBALL_DATA_ORG_KEY` | Calendario, classifiche e squadre della stagione corrente |
| `MARK_API_FOOTBALL_DAILY_LIMIT` | Limite giornaliero riservato alle chiamate API Football |

Il bootstrap continua anche senza queste chiavi usando le fonti pubbliche disponibili. Le integrazioni facoltative vengono indicate nella pagina Sistema.

## Sviluppo locale

Prepara la configurazione e avvia database, Redis, migrazioni, API e worker.

```bash
cp .env.example .env
make compose-up
```

Avvia il frontend in un altro terminale.

```bash
cd frontend
npm ci
npm run dev
```

Indirizzi locali:

- Frontend: [http://localhost:5173](http://localhost:5173)
- API: [http://localhost:8000](http://localhost:8000)
- Documentazione API: [http://localhost:8000/docs](http://localhost:8000/docs)
- Contratto OpenAPI: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

Per fermare i servizi di sviluppo:

```bash
make compose-down
```

## Componenti

- `frontend` contiene l'app React, le pagine e il sistema visuale
- `backend/src/markguardiola/api` contiene l'API FastAPI
- `backend/src/markguardiola/ingestion` contiene fonti, parser e pipeline dati
- `backend/src/markguardiola/features` costruisce le feature rispettando il tempo di disponibilità dei dati
- `backend/src/markguardiola/ml` gestisce training, calibrazione, valutazione e registro dei modelli
- `backend/src/markguardiola/decision` produce indicazioni per formazione, mercato e confronto con l'avversario
- `backend/alembic` contiene le migrazioni PostgreSQL
- `contracts` contiene il contratto OpenAPI usato dal frontend
- `infra` contiene immagini Docker e configurazioni Compose
- `scripts` contiene gli installer e la generazione del contratto API

## Dati locali

PostgreSQL conserva lo stato della lega e i dati canonici. Redis gestisce i job in background. Input scaricati e modelli allenati rimangono nei volumi Docker locali.

Il file `.env`, i dati acquisiti e i file prodotti dai modelli sono esclusi da Git.

## Licenza

Il codice è distribuito con licenza MIT. Consulta [LICENSE](./LICENSE).
