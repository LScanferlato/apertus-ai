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
| **Container runtime** | Docker >= 24 **o** Podman >= 5 + podman-compose >= 1.5 |
| **nvidia-container-toolkit** | Installato e configurato per il runtime prescelto |

Ottimizzato per GPU Pascal (compute 6.1) con tensor parallelism su 2 GPU.

## Prerequisiti (una tantum)

Prima del primo avvio, installare e configurare NVIDIA Container Toolkit per il
proprio runtime container:

### Ubuntu (automatico)
```bash
sudo bash setup-nvidia-container-toolkit.sh
```

### Ubuntu (manuale)
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

### openSUSE (automatico)
```bash
sudo bash setup-nvidia-container-toolkit.sh
```

### openSUSE (manuale)
```bash
sudo zypper addrepo --refresh \
  https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo
sudo zypper install nvidia-container-toolkit
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

## Avvio rapido

```bash
# (opzionale) token HuggingFace per pesi gated
export HF_TOKEN=hf_xxx

# Avvia lo stack (docker o podman)
docker compose up -d
# oppure: podman-compose up -d

# Monitora il download dei pesi (~9 GB) e l'avvio
docker compose logs -f vllm        # Docker
podman-compose logs -f vllm        # Podman

# Verifica lo stato
curl http://localhost:8080/health
```

Il primo avvio scarica i pesi del modello (~9 GB); puo richiedere alcuni minuti.

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

## Configurazioni

Il progetto include due file compose:

- **`docker-compose.yml`** — configurazione di produzione per 2x Quadro P4000 (16 GB VRAM). TP=2, contesto 16384.
- **`docker-compose.dev.yml`** — override per sviluppo su singola GPU (es. Quadro P2000 4 GB). TP=1, contesto 2048.
  ```bash
  sudo podman-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
  ```

> **Nota**: il modello Apertus 1.5 8B FP8 richiede ~9 GB di VRAM. Non puo funzionare
> su GPU con soli 4 GB. Il file dev.yml serve solo per test di infrastruttura.

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
