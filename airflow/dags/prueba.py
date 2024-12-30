from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import numpy as np
import json

def connect_mongodb():
    """Establece conexión con MongoDB"""
    try:
        client = MongoClient('mongodb://64.227.24.227:27017')
        db = client['facsat2']
        print("Conexión exitosa a MongoDB")
        return db
    except Exception as e:
        print(f"Error conectando a MongoDB: {e}")
        return None

def safe_get_nested(dictionary, *keys, default=None):
    """Obtiene de forma segura valores anidados en un diccionario"""
    try:
        value = dictionary
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default

def get_modules_info(db):
    """Obtiene información de los módulos"""
    modules_info = {}
    for module in db.Modules.find():
        module_id = module.get('_id', '')
        modules_info[module_id] = {
            'title': module.get('Title', ''),
            'type': module.get('Type', ''),
            'params': module.get('Params', [])
        }
    return modules_info

def get_beacon_info(db):
    """Obtiene información de beacons"""
    beacon_info = {}
    for beacon in db.BeaconTypes.find():
        beacon_id = beacon.get('_id', '')
        beacon_info[beacon_id] = {
            'auto_beacon_policy': beacon.get('auto_beacon_policy', ''),
            'bcsize': beacon.get('bcsize', 0),
            'description': beacon.get('description', ''),
            'max_samples': beacon.get('max_samples', 0),
            'samplerate': beacon.get('samplerate', ''),
            'type': beacon.get('type', ''),
            'version': beacon.get('version', '')
        }
    return beacon_info

def get_beacon_offsets(db):
    """Obtiene información de offsets de beacons"""
    offsets = {}
    for offset in db.BeaconOffsets.find():
        node = offset.get('Node')
        if node:
            offsets[node] = {
                'offset': offset.get('Offset', 0),
                'satellite': offset.get('Satellite', '')
            }
    return offsets

def get_flight_plan_info(db):
    """Obtiene información del plan de vuelo"""
    flight_plans = {}
    for plan in db.FlightPlan.find():
        plan_id = plan.get('code_fp', '')
        if plan_id:
            flight_plans[plan_id] = {
                'status': plan.get('status', ''),
                'created_at': plan.get('created_at', ''),
                'user': plan.get('user', ''),
                'banda_x': plan.get('banda_x', {}),
                'sync': plan.get('sync', {}),
                'readout': plan.get('readout', {}),
                'snap': plan.get('snap', {})
            }
    return flight_plans

def create_complete_dataframe(db):
    """Crea un DataFrame completo con información de todas las colecciones"""
    print("Iniciando creación del DataFrame completo...")
    
    # Obtener información de todas las colecciones
    modules_info = get_modules_info(db)
    beacon_info = get_beacon_info(db)
    beacon_offsets = get_beacon_offsets(db)
    flight_plans = get_flight_plan_info(db)
    
    # Lista para almacenar todos los datos
    all_data = []
    
    # Crear diccionario de información de parámetros
    param_info_dict = {}
    print("Procesando ParamInfo...")
    for info in db.ParamInfo.find():
        try:
            param_name = safe_get_nested(info, 'Param', 'Name')
            node_id = safe_get_nested(info, 'Param', 'Node')
            table_id = safe_get_nested(info, 'Param', 'Table')
            
            if all([param_name, node_id, table_id is not None]):
                key = (param_name, node_id, table_id)
                param_info_dict[key] = {
                    'unit': info.get('Unit', ''),
                    'type': info.get('Type', ''),
                    'help_text': info.get('HelpText', ''),
                    'default_value': info.get('DefaultValue', ''),
                    'size': info.get('Size', 0),
                    'count': info.get('Count', 0)
                }
        except Exception as e:
            print(f"Error procesando ParamInfo: {e}")
            continue

    # Procesar communication_log
    comm_logs = {}
    for log in db.communication_log.find():
        timestamp = log.get('created', '')
        if timestamp:
            comm_logs[timestamp] = {
                'communication_status': log.get('status', ''),
                'communication_type': log.get('type', ''),
                'communication_detail': log.get('detail', {}),
                'communication_tasks': log.get('task', [])
            }

    # Procesar datos actuales
    print("Procesando ParamData_Latest...")
    for doc in db.ParamData_Latest.find():
        try:
            param = doc.get('Param', {})
            if not param:
                continue
                
            node_id = param.get('Node')
            param_name = param.get('Name')
            table_id = param.get('Table')
            timestamp = datetime.fromtimestamp(doc.get('Ts', 0))
            
            if not all([node_id, param_name, table_id]):
                continue
            
            # Obtener información adicional del parámetro
            param_info = param_info_dict.get((param_name, node_id, table_id), {})
            
            # Obtener información del beacon offset
            beacon_offset = beacon_offsets.get(node_id, {})
            
            # Buscar información de comunicación cercana
            comm_info = {}
            for comm_time, comm_data in comm_logs.items():
                if comm_time and abs((datetime.strptime(comm_time, '%Y-%m-%d %H:%M:%S') - timestamp).total_seconds()) < 300:
                    comm_info = comm_data
                    break

            entry = {
                # Información básica del parámetro
                'timestamp': timestamp,
                'parameter_name': param_name,
                'value': doc.get('Val', None),
                'node_id': node_id,
                'table_id': table_id,
                'satellite_id': param.get('Satellite', ''),
                
                # Información detallada del parámetro
                'unit': param_info.get('unit', ''),
                'param_type': param_info.get('type', ''),
                'description': param_info.get('help_text', ''),
                'default_value': param_info.get('default_value', ''),
                'size_bytes': param_info.get('size', 0),
                'param_count': param_info.get('count', 0),
                
                # Información de beacon
                'beacon_offset': beacon_offset.get('offset', ''),
                'beacon_satellite': beacon_offset.get('satellite', ''),
                
                # Información de comunicación
                'comm_status': comm_info.get('communication_status', ''),
                'comm_type': comm_info.get('communication_type', ''),
                'orbit_number': safe_get_nested(comm_info, 'communication_detail', 'orbit', default=''),
                'elevation': safe_get_nested(comm_info, 'communication_detail', 'elevation', default=''),
                'azimuth': safe_get_nested(comm_info, 'communication_detail', 'azimuth', default=''),
                'latitude': safe_get_nested(comm_info, 'communication_detail', 'latitud', default=''),
                'longitude': safe_get_nested(comm_info, 'communication_detail', 'longitud', default='')
            }
            
            all_data.append(entry)
            
        except Exception as e:
            print(f"Error procesando documento: {e}")
            continue

    # Crear DataFrame
    if not all_data:
        print("No se encontraron datos para procesar")
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    
    # Agregar valor normalizado
    print("Calculando valores normalizados...")
    df['value_normalized'] = df.groupby('parameter_name')['value'].transform(
        lambda x: (x - x.min()) / (x.max() - x.min()) if x.max() != x.min() else 0
    )
    
    # Convertir tipos de datos apropiados
    numeric_columns = ['value', 'elevation', 'azimuth', 'latitude', 'longitude']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='ignore')
    
    print(f"DataFrame creado exitosamente con {len(df)} registros")
    return df

def main():
    """Función principal"""
    print("Iniciando procesamiento de datos...")
    
    # Conectar a MongoDB
    db = connect_mongodb()
    if db is None:
        return
    
    # Crear DataFrame
    df = create_complete_dataframe(db)
    
    if df.empty:
        print("No se pudieron obtener datos")
        return
    
    # Guardar a CSV
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'facsat2_complete_telemetry_{timestamp}.csv'
    df.to_csv(csv_filename, index=False)
    
    # Mostrar estadísticas
    print("\nEstadísticas del DataFrame:")
    print(f"\nTotal de registros: {len(df)}")
    print("\nColumnas disponibles:")
    for col in df.columns:
        non_null = df[col].count()
        print(f"{col}: {non_null} valores no nulos")
    
    print("\nEstadísticas numéricas básicas:")
    print(df.describe())
    
    print(f"\nArchivo guardado como: {csv_filename}")

if __name__ == "__main__":
    main()