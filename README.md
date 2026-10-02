# Visualizador de Telemetría Modular

## Ejecución

```bash
python run.py
```

## Estructura

- `run.py`: único punto de entrada.
- `app/config.py`: configuración general, conexión y rutas.
- `app/database.py`: acceso a MySQL.
- `app/processing.py`: preparación de datos y cálculos de turnos.
- `app/time_ranges.py`: rangos operacionales 07:00–07:00.
- `app/reports.py`: generación y actualización persistente de `MapaAgua.xlsx`.
- `app/ui.py`: interfaz Tkinter y acciones de usuario.

## Archivo MapaAgua.xlsx

La aplicación actualiza un único libro y conserva las hojas mensuales creadas en ejecuciones anteriores.

Hojas de control:

- `Agua_Resumen`: resumen operativo actual.
- `Agua_Tendencia`: copia compatible del mes vigente para no romper el dashboard existente.
- `Indice_Meses`: catálogo que relaciona cada período con su hoja mensual.

Hojas mensuales:

- `Agosto_2026`
- `Julio_2026`
- `Junio_2026`
- `Mayo_2026`
- etc.

El nombre incluye el año para evitar colisiones cuando exista, por ejemplo, agosto de 2026 y agosto de 2027.

## Comportamiento acumulativo

Con `TELEMETRIA_MESES_HISTORICOS=3`, durante agosto se actualizan:

- `Agosto_2026`, en curso;
- `Julio_2026`, cerrado;
- `Junio_2026`, cerrado;
- `Mayo_2026`, cerrado.

Al comenzar septiembre:

- se crea `Septiembre_2026`;
- `Agosto_2026` se recalcula como mes cerrado;
- las hojas más antiguas, como `Mayo_2026`, se conservan aunque ya no estén dentro de la ventana de recálculo.

Por lo tanto, el libro crece mes a mes y no pierde el histórico acumulado.

## Índice para el dashboard

`Indice_Meses` contiene:

- período `AAAA-MM`;
- nombre de la hoja;
- estado `En curso` o `Cerrado`;
- rango operacional;
- cantidad de filas;
- fecha de actualización.

El Apps Script puede leer este índice para resolver dinámicamente qué hoja corresponde al mes seleccionado.

## Variables de entorno opcionales

```text
TELEMETRIA_DB_HOST
TELEMETRIA_DB_PORT
TELEMETRIA_DB_USER
TELEMETRIA_DB_PASSWORD
TELEMETRIA_DB_NAME
TELEMETRIA_OUTPUT_DIR
TELEMETRIA_MESES_HISTORICOS
```

## Dependencias

```bash
python -m pip install -r requirements.txt
```

## Consideración operativa

`MapaAgua.xlsx` debe estar cerrado en Excel al momento de generarlo, ya que Windows bloquea el reemplazo de archivos abiertos.
