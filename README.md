# Apertus Translation Container

Container per traduzione AI in-house basato su **Apertus 1.5 8B**, il modello
LLM open-source svizzero (ETH Zürich / EPFL / CSCS). Ispirato al sistema
installato dall'azienda ticinese **Artificialy** per il Canton Ticino
([CSCS, marzo 2026](https://www.cscs.ch/science/computer-science-hpc/2026/apertus-powers-in-house-ai-translation-for-ticino)).

## Caratteristiche

- **Fully on-prem**: hardware e modello sotto controllo, dati sensibili non
  escono dal perimetro (come richiesto dalla Pubblica Amministrazione ticinese).
- **Modello**: `artificialy/Apertus-v1.5-8B-FP8-DYNAMIC` — la quantizzazione FP8
  di Apertus 1.5 8B pubblicata proprio da Artificialy (GPU >= 16 GB VRAM).
- **Backend inferenza**: immagine Docker ufficiale Swiss-AI
  `ghcr.io/swiss-ai/vllm_apertus_1.5_release` (vLLM con patch per Apertus 1.5
  multimodale preinstallate).
- **API esposte**:
  - `POST /translate` — endpoint **DeepL-style** (JSON semplificato).
  - `POST /translate/batch` — traduzione multipli testi.
  - `POST /v1/chat/completions`, `GET /v1/models` — **OpenAI-compatible** in
    passthrough verso vLLM.
- Nginx opzionale per TLS termination.
- Healthcheck end-to-end.

> ⚠️ **Nota su Ollama**: Apertus 1.5 è **multimodale** (testo + image + audio) e
> al momento non esistono build GGUF attendibili del modello né supporto nativo
> in Ollama per questa architettura. Si usa quindi vLLM (backend ufficialmente
> raccomandato da Swiss-AI), che tra l'altro espone già una API
> OpenAI-compatible.

## Requisiti

- Docker >= 24 + plugin `nvidia-container-toolkit`
- GPU NVIDIA con **>= 16 GB VRAM** (FP8), oppure >= 24 GB per BF16
- (opzionale) `HF_TOKEN` se necessario per il download dei pesi

## Avvio rapido

```bash
# 1) (opzionale) token HuggingFace, se serve accedere ai pesi gated
export HF_TOKEN=hf_xxx

# 2) Avvia lo stack
docker compose up -d

# 3) Verifica lo stato (il primo avvio scarica ~9 GB di pesi)
docker compose logs -f vllm
curl http://localhost:8080/health
```

## Uso

### Endpoint DeepL-style `POST /translate`

```bash
curl -X POST http://localhost:8080/translate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The Canton of Ticino is the southernmost canton of Switzerland.",
    "source_lang": "English",
    "target_lang": "Italian",
    "context": "public administration"
  }'
```

Risposta:

```json
{
  "translations": [{"text": "Il Canton Ticino è il cantone più meridionale della Svizzera.", "target_lang": "Italian"}],
  "detected_source_lang": "English",
  "model": "apertus-translator",
  "usage": {"prompt_tokens": 87, "completion_tokens": 18, "total_tokens": 105},
  "timings": {"total": 0.42}
}
```

### Endpoint OpenAI-compatible

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "apertus-translator",
    "messages": [
      {"role": "system", "content": "You are a professional translator."},
      {"role": "user", "content": "Translate to Italian: Good morning"}
    ]
  }'
```

### Batch

```bash
curl -X POST http://localhost:8080/translate/batch \
  -H "Content-Type: application/json" \
  -d '{"texts":["Hello","Goodbye"],"target_lang":"Italian"}'
```

## Lingue supportate

Apertus è multilingue fin dall'inizio (> 1000 lingue). Per il caso d'uso svizzero
il prompt di sistema è ottimizzato per: italiano, tedesco, francese, romancio,
più inglese, spagnolo, rumeno, ucraino (come menzionato nell'articolo CSCS).

## Struttura

```
apertus-translator/
├── docker-compose.yml    # stack: vllm + api (+ nginx opzionale)
├── api/
│   ├── Dockerfile         # FastAPI gateway
│   ├── main.py            # /translate + proxy OpenAI
│   └── requirements.txt
└── nginx/
    ├── nginx.conf         # TLS termination (profilo "tls")
    └── certs/             # metter qui fullchain.pem e privkey.pem
```

## TLS opzionale

```bash
mkdir -p nginx/certs
cp /percorso/fullchain.pem nginx/certs/
cp /percorso/privkey.pem  nginx/certs/
docker compose --profile tls up -d
```

## Parametri principali (env in `docker-compose.yml`)

| Variabile             | Default                                  | Descrizione                              |
|-----------------------|------------------------------------------|------------------------------------------|
| `MODEL_NAME`          | apertus-translator (vLLM served name)    | nome servito da vLLM                     |
| `VLLM_BASE_URL`       | http://vllm:8000                         | URL backend vLLM                        |
| `DEFAULT_TARGET_LANG` | Italian                                  | lingua di default per /translate/batch   |
| `MAX_TEXT_CHARS`      | 50000                                    | dimensione max testo                     |
| `HF_TOKEN`            | -                                        | token HuggingFace per pesi gated          |

## Note legali / etiche

Apertus è distribuito con licenza **Apache 2.0**, training data e pipeline
fully open-source. Per uso in Pubblica Amministrazione vedi la documentazione
EU AI Act pubblicata da Swiss-AI:
<https://github.com/swiss-ai/apertus-legal>.
