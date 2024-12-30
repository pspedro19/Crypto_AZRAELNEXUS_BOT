# CRYPTO AZRAEL NEXUS BOT 🤖

![Azrael Nexus](https://via.placeholder.com/800x200?text=AZRAEL+NEXUS+BOT)

## Descripción
AZRAEL NEXUS es un bot de trading algorítmico avanzado diseñado para operar en el mercado de criptomonedas, específicamente en Binance. Utiliza una combinación de aprendizaje automático, análisis técnico y gestión de riesgos adaptativa para identificar y ejecutar operaciones de trading.

## Características Principales 🚀

### Análisis de Mercado
- Análisis en tiempo real de patrones de mercado.
- Detección de estados de mercado mediante HMM (Hidden Markov Models).
- Indicadores técnicos avanzados y análisis de volatilidad.
- Identificación de niveles de soporte y resistencia.

### Sistema de Trading
- Trading spot automatizado.
- Gestión dinámica de posiciones.
- Sistema de stop-loss adaptativo.
- Toma de beneficios basada en análisis de mercado.

### Visualización de Datos 📊
- Dashboard interactivo en tiempo real.
- Gráficos de precio y estados del mercado.
- Métricas de rendimiento y estadísticas.
- Panel de alertas y señales.

### Gestión de Riesgos 🛡️
- Control dinámico del tamaño de posiciones.
- Sistema de gestión de drawdown.
- Análisis de correlación y exposición.
- Protección contra condiciones anómalas de mercado.

## Estructura del Proyecto 📂
```plaintext
.
├── .dockerignore
├── .env
├── .git
├── .gitignore
├── .venv
├── README.md
├── airflow/
│   ├── Dockerfile
│   ├── airflow.cfg
│   ├── dags/
│   ├── entrypoint.sh
│   ├── logs/
│   ├── plugins/
│   ├── requirements.txt
│   ├── secrets/
│   └── wait-for-it.sh
├── app/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── data/
│   └── facsat2/
├── docker-compose.yaml
├── ejecucion.log
├── facsat2.zip
├── init-mongodb/
│   ├── healthcheck.sh
│   ├── init-replicaset.sh
│   ├── init-secondary.sh
│   └── init-standalone.sh
├── minio/
│   ├── Dockerfile
│   └── data/
├── mlflow/
│   ├── Dockerfile
│   ├── init_db.sh
│   └── requirements.txt
├── notebooks/
│   ├── descriptivas_ParamData.ipynb
│   ├── entendimiento_datos.ipynb
│   ├── exploratory_data_analysis.ipynb
│   ├── outputs/
│   └── proceso_etl.ipynb
└── requirements.txt
## Instalación y Configuración 🛠️

### Requisitos del Sistema
- **Python**: >= 3.8
- **Docker**: >= 20.10
- **Docker Compose**: >= 1.29

### Pasos de Instalación

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/yourusername/crypto_azraelnexus_bot.git
   cd crypto_azraelnexus_bot

2. Crear un entorno virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   .venv\Scripts\activate     # Windows

3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt

4. Configurar variables de entorno:
   ```bash
   cp .env.example .env
   # Edita el archivo .env con las claves y configuraciones necesarias

5. Construir servicios Docker:
   ```bash
   docker-compose up --build


