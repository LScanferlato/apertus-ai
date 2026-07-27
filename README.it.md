# Apertus Translation Container

Container per traduzione AI in-house basato su **Apertus 1.5 8B**, modello
LLM open-source svizzero (ETH Zurigo / EPFL / CSCS). Ispirato al sistema
installato dall'azienda ticinese **Artificialy** per il Canton Ticino.

## Requisiti hardware

| Componente | Specifica |
|------------|-----------|
| **GPU** | 2x NVIDIA Quadro P4000 (8 GB VRAM cad.) |
| **VRAM totale** | 16 GB |
| **RAM** | >= 32 GB |
| **Storage** | >= 20 GB liberi (modello ~9 GB) |
| **Docker** | >= 24 + nvidia-container-toolkit |

Ottimizzato per GPU Pascal (compute 6.1) con tensor parallelism su 2 GPU.

## Avvio rapido

```bash
# (opzionale) token HuggingFace per pesi gated
export HF_TOKEN=hf_xxx

# Avvia lo stack
docker compose up -d

# Monitora il download dei pesi (~9 GB) e l'avvio
docker compose logs -f vllm

# Verifica lo stato
curl http://localhost:8080/health
```

Il primo avvio scarica i pesi del modello; puo richiedere alcuni minuti.

## Endpoint

### Traduzione DeepL-style

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

### Batch

```bash
curl -X POST http://localhost:8080/translate/batch \
  -H "Content-Type: application/json" \
  -d '{"texts":["Hello","Goodbye"],"target_lang":"Italian"}'
```

### API OpenAI-compatible

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

## Configurazione ottimizzata per 2x Quadro P4000

Il file `docker-compose.yml` include ottimizzazioni specifiche per GPU Pascal:

| Parametro | Valore | Perche |
|-----------|--------|--------|
| `tensor-parallel-size` | 2 | Divide il modello su entrambe le GPU |
| `enforce-eager` | attivo | Pascal non supporta CUDA graphs |
| `gpu-memory-utilization` | 0.92 | Usa ~7.4 GB degli 8 GB disponibili |
| `max-model-len` | 16384 | Contest sufficiente per traduzione, risparmia VRAM |
| `max-num-seqs` | 128 | Throughput bilanciato senza OOM |
| `kv-cache-dtype` | fp8 | KV cache in FP8, allineata al modello |
| `block-size` | 16 | Blocchi piccoli, meno spreco di VRAM |
| `num-scheduler-steps` | 8 | Pipeline per miglior throughput |
| `count` (deploy) | 2 | Docker riserva entrambe le GPU |

## Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `MODEL_NAME` | apertus-translator | Nome modello servito da vLLM |
| `VLLM_BASE_URL` | http://vllm:8000 | URL backend vLLM |
| `DEFAULT_TARGET_LANG` | Italian | Lingua target di default |
| `MAX_TEXT_CHARS` | 50000 | Dimensione massima testo per richiesta |
| `HF_TOKEN` | - | Token HuggingFace per modelli gated |

## Struttura del progetto

```
apertus-translator/
├── docker-compose.yml    # stack: vllm + api + nginx (opzionale)
├── api/
│   ├── Dockerfile         # FastAPI gateway
│   ├── main.py            # /translate + proxy OpenAI
│   └── requirements.txt
├── nginx/
│   └── nginx.conf         # TLS termination
├── README.md              # Documentazione inglese
└── README.it.md           # Documentazione italiana
```

## TLS (opzionale)

```bash
mkdir -p nginx/certs
cp /percorso/fullchain.pem nginx/certs/
cp /percorso/privkey.pem  nginx/certs/
docker compose --profile tls up -d
```

## Lingue supportate

Apertus e multilingue (> 1000 lingue). Ottimizzato via system prompt per:
italiano, tedesco, francese, romancio, inglese, spagnolo, rumeno, ucraino.

## Note

- Il modello Apertus 1.5 e **multimodale** (testo + immagine + audio).
- vLLM e il backend ufficialmente raccomandato da Swiss-AI.
- Licenza: Apache 2.0.
