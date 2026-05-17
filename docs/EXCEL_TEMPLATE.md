# Plantilla Excel Oficial (Fase 3)

La plantilla es la unica entrada formal de la plataforma. Esta diseniada
para ser diligenciada por usuarios de negocio con minimo riesgo de
errores.

## Hojas

| Hoja            | Proposito                                                        |
| --------------- | ---------------------------------------------------------------- |
| `Instrucciones` | Reglas y formato de diligenciamiento.                            |
| `Proceso`       | Metadata del proceso (1 fila).                                    |
| `Actividades`   | Una fila por actividad/evento/compuerta del proceso.             |
| `Catalogos`     | Catalogos cargados desde `catalogs/*.yaml`. Solo lectura.        |

## Columnas de `Actividades`

| Columna             | Tipo      | Catalogo    | Reglas |
| ------------------- | --------- | ----------- | ------ |
| ID                  | ID        | -           | Unico; >=3 caracteres. |
| ID Proceso          | ID        | -           | Debe existir en hoja Proceso. |
| Tipo BPMN           | Dropdown  | bpmn_types  | Subset gobernado. |
| Actividad           | Texto     | -           | Formato `Verbo + Objeto [+ Contexto]`. |
| Responsable         | Dropdown  | roles       | Catalogo controlado. |
| Sistema             | Dropdown  | systems     | Catalogo controlado. |
| Comando             | Texto     | -           | Debe pertenecer al Sistema indicado. |
| API                 | Texto     | -           | Identificador o endpoint. |
| Entrada             | Texto     | -           | Insumo / DataObject. |
| Salida              | Texto     | -           | Resultado producido. |
| Activo Informacion  | Texto     | -           | Activo principal asociado. |
| Riesgo              | Dropdown  | risks       | Catalogo controlado. |
| Control             | Dropdown  | controls    | Catalogo controlado. |
| SLA                 | Duracion  | -           | Formato `2h`, `30m`, `1d`, `45s`. |
| KPI                 | Texto     | -           | Indicador asociado. |
| Observaciones       | Texto     | -           | Notas para el agente semantico. |

## Validaciones integradas en el .xlsx

- **Dropdowns**: tipo BPMN, sistema, responsable, riesgo, control.
- **SLA**: formula que valida sufijos `h|m|s|d`.
- **IDs**: longitud minima 3 caracteres en columnas obligatorias.
- **Encabezados destacados** y fila de ayuda inmediatamente debajo.

## Generacion

Desde la app: **Archivo -> Generar plantilla Excel...**

Desde la CLI:

```powershell
bpmn-template -o .\plantilla.xlsx --rows 100
```

## Edicion de catalogos

1. Modificar archivos en `catalogs/*.yaml`.
2. Regenerar la plantilla (los dropdowns se reconstruyen con los nuevos
   valores).
3. En la app: **Herramientas -> Recargar catalogos** (`F5`).
