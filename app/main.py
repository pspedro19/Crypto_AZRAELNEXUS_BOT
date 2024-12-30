from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware

# Inicializar FastAPI
app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo para los datos de entrada
class DataInput(BaseModel):
    data: List[Dict[Any, Any]]
    question: str

    class Config:
        arbitrary_types_allowed = True

# Función simple de procesamiento
def process_data(df: pd.DataFrame, question: str) -> str:
    try:
        # Ejemplo de procesamiento básico
        num_rows = len(df)
        num_cols = len(df.columns)
        column_names = ", ".join(df.columns)
        
        # Crear una respuesta básica
        response = f"""
        Análisis básico del DataFrame:
        - Número de filas: {num_rows}
        - Número de columnas: {num_cols}
        - Columnas disponibles: {column_names}
        - Pregunta realizada: {question}
        """
        
        # Si hay columnas numéricas, agregar estadísticas básicas
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        if len(numeric_cols) > 0:
            stats = df[numeric_cols].describe()
            response += "\nEstadísticas básicas de columnas numéricas:\n"
            response += str(stats)
            
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando datos: {str(e)}")

# Endpoint para el chat
@app.post("/chat/")
async def chat_endpoint(data_input: DataInput):
    try:
        # Convertir los datos de entrada en DataFrame
        df = pd.DataFrame(data_input.data)
        
        # Procesar los datos
        result = process_data(df, data_input.question)
        
        return {"response": result}
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Error en los datos de entrada: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

# Endpoint de salud
@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Endpoint raíz
@app.get("/")
def read_root():
    return {"message": "Bienvenido a la API de procesamiento de datos"}